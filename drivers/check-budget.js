async (page) => {
  const text = await page.getByRole('dialog').getByRole('alert').innerText();
  if (!text.includes('Error Code: 422') || !text.includes('qa42689-budget') || !text.includes('Current cost: 1.0, Max budget: 0.01')) {
    throw new Error(text);
  }
  return {url: page.url(), budgetFailureVisible: true, status: 422};
}
