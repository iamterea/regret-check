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

export const MAX_COMPARE = 4;

export type ParsedRepos = { repos: string[] } | { error: string };

/** One or more repositories separated by spaces, commas or new lines → unique "owner/name" list, or an error to show. */
export function parseRepos(input: string): ParsedRepos {
  const parts = input.split(/[\s,]+/).filter(Boolean);
  if (parts.length === 0) return { error: "Enter a GitHub repository as owner/name or paste its URL." };
  const repos: string[] = [];
  for (const part of parts) {
    const repo = parseRepo(part);
    if (!repo) return { error: `"${part}" is not a GitHub repository. Use owner/name or paste its URL.` };
    if (!repos.some((seen) => seen.toLowerCase() === repo.toLowerCase())) repos.push(repo);
  }
  if (repos.length > MAX_COMPARE) return { error: `Compare at most ${MAX_COMPARE} repositories at a time.` };
  return { repos };
}
