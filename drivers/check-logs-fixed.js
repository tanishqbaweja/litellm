async (page) => {
  await page.getByText('Showing 1-4 of 4', {exact: true}).waitFor({state: 'visible'});
  const rows = (await page.getByRole('table').getByRole('row').allTextContents()).slice(1);
  const observations = {
    url: page.url(),
    rows: rows.length,
    failures: rows.filter(value => value.includes('Failure')).length,
    successes: rows.filter(value => value.includes('Success')).length,
    expired: rows.filter(value => value.includes('qa42689-expired')).length,
    budget: rows.filter(value => value.includes('qa42689-budget')).length,
    valid: rows.filter(value => value.includes('qa42689-valid')).length,
    pagination: await page.getByText('Showing 1-4 of 4', {exact: true}).innerText(),
  };
  if (observations.rows !== 4 || observations.failures !== 3 || observations.successes !== 1 || observations.expired !== 2 || observations.budget !== 1 || observations.valid !== 1) {
    throw new Error(JSON.stringify(observations));
  }
  return observations;
}
