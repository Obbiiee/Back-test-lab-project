// Gate the existing action before it pauses, loads or resets anything.
export function requestAccountReset(account, action, requestConfirmation) {
  if (['orders', 'positions', 'trades'].some(key => account[key]?.length > 0)) requestConfirmation(action);
  else return action();
}
