const OWNER = /^[A-Za-z0-9-]{1,39}$/;
const NAME = /^[A-Za-z0-9._-]{1,100}$/;

/** "owner/name" or any github.com URL → "owner/name"; null when it is neither. */
export function parseRepo(input: string): string | null {
  const path = input
    .trim()
    .split(/[?#]/)[0]
    .replace(/^(https?:\/\/)?(www\.)?github\.com\//i, "");
  const [owner, rawName] = path.split("/");
  if (!owner || !rawName) return null;
  const name = rawName.replace(/\.git$/i, "");
  return OWNER.test(owner) && NAME.test(name) ? `${owner}/${name}` : null;
}
