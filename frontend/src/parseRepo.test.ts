import { describe, expect, it } from "vitest";
import { parseRepo } from "./parseRepo";

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
