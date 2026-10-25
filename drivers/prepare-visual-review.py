import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path, PurePosixPath

from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent
revision = sys.argv[1]
assert revision in ('baseline', 'fixed')
output = root / 'visual-review-final'
output.mkdir(exist_ok=True)
font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 16)
manifest = {'revision': revision, 'raw_screenshots': [], 'screenshot_contact_sheets': [], 'recordings': []}


def local(linux_path):
    relative = PurePosixPath(linux_path).relative_to(PurePosixPath('/qa/litellm-35800'))
    result = root.joinpath(*relative.parts)
    assert result.resolve().is_relative_to(root.resolve())
    return result


def sheet(files, target, viewport):
    width, height = (390, 844) if viewport == 'phone' else (720, 450)
    columns = 4 if viewport == 'phone' else 2
    canvas = Image.new('RGB', (columns * width, math.ceil(len(files) / columns) * (height + 30)), '#eeeeee')
    draw = ImageDraw.Draw(canvas)
    for index, file in enumerate(files):
        with Image.open(file) as image:
            source = image.convert('RGB')
        source.thumbnail((width, height))
        x = index % columns * width
        y = index // columns * (height + 30)
        draw.text((x + 4, y + 5), file.stem, fill='black', font=font)
        canvas.paste(source, (x, y + 30))
    canvas.save(target)


report = json.loads((root / f'ui-report-{revision}.json').read_text(encoding='utf-8'))
assert report.get('completedAt') and report['result'] == 'passed'
visual = local(report['output'])
manifest['source_sha'] = report['sourceSha']
for viewport in report['viewports']:
    assert viewport['result'] == 'passed'
    name = viewport['viewport']['name']
    files = [visual / step['screenshot'] for step in viewport['steps']]
    assert len(files) == 7
    for file in files:
        assert file.is_file()
        manifest['raw_screenshots'].append({'path': file.relative_to(root).as_posix(), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
    for index in range(0, len(files), 4):
        target = output / f'{revision}-{name}-screenshots-{index // 4 + 1}.png'
        sheet(files[index:index + 4], target, name)
        manifest['screenshot_contact_sheets'].append(target.relative_to(root).as_posix())
    video = viewport['video']
    probe = subprocess.run(['docker', 'exec', 'contri-litellm-47520', 'ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', video], capture_output=True, text=True, check=True)
    duration = float(json.loads(probe.stdout)['format']['duration'])
    frames = []
    for index in range(8):
        seconds = duration * (index + 0.5) / 8
        filename = f'{revision}-{name}-frame-{index + 1}-{seconds:.2f}s.png'
        target = output / filename
        subprocess.run(['docker', 'exec', 'contri-litellm-47520', 'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(seconds), '-i', video, '-frames:v', '1', '-update', '1', '/qa/litellm-35800/visual-review-final/' + filename], check=True)
        frames.append(target)
    sheets = []
    for index in range(0, 8, 4):
        target = output / f'{revision}-{name}-video-{index // 4 + 1}.png'
        sheet(frames[index:index + 4], target, name)
        sheets.append(target.relative_to(root).as_posix())
    manifest['recordings'].append({'revision': revision, 'source_sha': report['sourceSha'], 'viewport': name, 'video': local(video).relative_to(root).as_posix(), 'duration_seconds': duration, 'sampled_frames': [file.relative_to(root).as_posix() for file in frames], 'contact_sheets': sheets})
    print(json.dumps({'revision': revision, 'viewport': name, 'screenshots': len(files), 'video_seconds': duration}), flush=True)
(output / f'manifest-{revision}.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
