// Deliberately small eager gate: the verifier/view remain in the lazy review chunk.
export function isLocalReview(hostname){return ['localhost','127.0.0.1','[::1]','::1'].includes(hostname);}
