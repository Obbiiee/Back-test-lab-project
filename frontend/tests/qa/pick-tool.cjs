// Choose a drawing tool the way the current layout offers it: the left rail on laptop/tablet,
// or the Draw bottom sheet (tabs per tool group) on phones, where the rail is hidden.
module.exports = async function pickTool(page, group, name) {
  const rail = page.getByLabel(`${group} drawing tools`);
  if (await rail.isVisible()) { await rail.click(); await page.getByRole('button', { name, exact: true }).click(); return 'rail'; }
  await page.getByRole('button', { name: 'Draw', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Drawing tools' });
  await sheet.getByRole('tab', { name: group, exact: true }).click();
  await sheet.getByRole('button', { name, exact: true }).click();
  await sheet.waitFor({ state: 'detached' });
  return 'sheet';
};
