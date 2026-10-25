async (page) => {
  const text = await page.getByRole('tabpanel', {name: 'Overview', exact: true}).innerText();
  const summary = text.match(/Spend\s+([^\n]+)\s+No budget set\s+Total Requests\s+(\d+)\s+(\d+) ok\s+(\d+) failed\s+Total Tokens\s+(\d+)/);
  if (!summary || summary[1] !== '$0.06' || summary[2] !== '9' || summary[3] !== '1' || summary[4] !== '8' || summary[5] !== '36') {
    throw new Error(text.slice(0, 500));
  }
  const keyTable = page.getByRole('table').filter({has: page.getByRole('columnheader', {name: 'Key ID', exact: true})});
  const keyRows = (await keyTable.getByRole('row').allTextContents()).slice(1);
  if (keyRows.length !== 3 || !['qa42689-valid', 'qa42689-budget', 'qa42689-expired'].every(alias => keyRows.some(row => row.includes(alias)))) {
    throw new Error('Spend breakdown must contain only the three recognized keys');
  }
  if (!text.includes('Avg cost / request\n$0.0150')) {
    throw new Error('Average cost must use the four retained spend records');
  }
  return {url: page.url(), spend: summary[1], requests: Number(summary[2]), successful: Number(summary[3]), failed: Number(summary[4]), tokens: Number(summary[5])};
}
