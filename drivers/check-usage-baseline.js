async (page) => {
  const text = await page.getByRole('tabpanel', {name: 'Overview', exact: true}).innerText();
  const summary = text.match(/Spend\s+([^\n]+)\s+No budget set\s+Total Requests\s+(\d+)\s+(\d+) ok\s+(\d+) failed\s+Total Tokens\s+(\d+)/);
  if (!summary || summary[1] !== '$0.06' || summary[2] !== '9' || summary[3] !== '1' || summary[4] !== '8' || summary[5] !== '36') {
    throw new Error(text.slice(0, 500));
  }
  return {url: page.url(), spend: summary[1], requests: Number(summary[2]), successful: Number(summary[3]), failed: Number(summary[4]), tokens: Number(summary[5])};
}
