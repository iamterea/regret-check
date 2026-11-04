import { useState, type FormEvent } from "react";
import { MAX_COMPARE, parseRepos } from "../parseRepo";

const EXAMPLES = [
  { repo: "django/django", note: "very active" },
  { repo: "moment/moment", note: "maintenance mode" },
  { repo: "request/request", note: "deprecated" },
  { repo: "atom/atom", note: "archived" },
];

const COMPARE_EXAMPLE = ["moment/moment", "date-fns/date-fns", "iamkun/dayjs", "moment/luxon"];

interface Props {
  onSubmit: (fullNames: string[]) => void;
  disabled: boolean;
}

export function RepoForm({ onSubmit, disabled }: Props) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = parseRepos(text);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    setError(null);
    onSubmit(parsed.repos);
  }

  function pick(repos: string[]) {
    setText(repos.join(", "));
    setError(null);
    onSubmit(repos);
  }

  return (
    <form className="repo-form" onSubmit={submit} noValidate>
      <label htmlFor="repo">GitHub repository</label>
      <div className="repo-form__row">
        <input
          id="repo"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="owner/name, or several to compare"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error !== null}
          aria-describedby={error ? "repo-hint repo-error" : "repo-hint"}
        />
        <button type="submit" disabled={disabled}>
          Check
        </button>
      </div>
      <p id="repo-hint" className="form-hint">
        One repository, or up to {MAX_COMPARE} separated by spaces or commas to compare them side by side.
      </p>
      {error && (
        <p id="repo-error" className="form-error" role="alert">
          {error}
        </p>
      )}
      <p className="examples">
        Try:
        {EXAMPLES.map(({ repo, note }) => (
          <button key={repo} type="button" className="chip" disabled={disabled} onClick={() => pick([repo])}>
            {repo} <span className="chip__note">{note}</span>
          </button>
        ))}
        <button type="button" className="chip chip--compare" disabled={disabled} onClick={() => pick(COMPARE_EXAMPLE)}>
          Compare date libraries <span className="chip__note">4 repos</span>
        </button>
      </p>
    </form>
  );
}
