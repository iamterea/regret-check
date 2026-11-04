import { describe, expect, it } from "vitest";
import { parseRepo, parseRepos } from "./parseRepo";

describe("parseRepo", () => {
  it.each([
    ["django/django", "django/django"],
    ["  django/django  ", "django/django"],
    ["https://github.com/django/django", "django/django"],
    ["http://www.github.com/django/django/", "django/django"],
    ["github.com/django/django.git", "django/django"],
    ["https://github.com/facebook/react/tree/main/packages", "facebook/react"],
    ["https://github.com/psf/requests?tab=readme-ov-file#readme", "psf/requests"],
  ])("reads %s", (input, expected) => {
    expect(parseRepo(input)).toBe(expected);
  });

  it.each(["", "django", "not a repo", "owner/na me", "https://gitlab.com/group/project"])(
    "rejects %j",
    (input) => {
      expect(parseRepo(input)).toBeNull();
    },
  );
});

describe("parseRepos", () => {
  it("reads one repository", () => {
    expect(parseRepos("django/django")).toEqual({ repos: ["django/django"] });
  });

  it("reads several separated by commas, spaces and new lines", () => {
    expect(parseRepos("moment/moment, https://github.com/date-fns/date-fns\niamkun/dayjs")).toEqual({
      repos: ["moment/moment", "date-fns/date-fns", "iamkun/dayjs"],
    });
  });

  it("drops duplicates, ignoring case", () => {
    expect(parseRepos("a/b A/B https://github.com/a/b")).toEqual({ repos: ["a/b"] });
  });

  it("names the part that is not a repository", () => {
    expect(parseRepos("a/b nope")).toEqual({
      error: '"nope" is not a GitHub repository. Use owner/name or paste its URL.',
    });
  });

  it("asks for input when empty", () => {
    expect(parseRepos("   ")).toEqual({ error: "Enter a GitHub repository as owner/name or paste its URL." });
  });

  it("limits a comparison to four repositories", () => {
    expect(parseRepos("a/a b/b c/c d/d e/e")).toEqual({ error: "Compare at most 4 repositories at a time." });
  });
});
