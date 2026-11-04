import { useState, type FormEvent } from "react";
import { parseRepo } from "../parseRepo";

const EXAMPLES = [
  { repo: "django/django", note: "very active" },
  { repo: "moment/moment", note: "maintenance mode" },
  { repo: "request/request", note: "deprecated" },
  { repo: "atom/atom", note: "archived" },
];

interface Props {
  onSubmit: (fullName: string) => void;
  disabled: boolean;
}

export function RepoForm({ onSubmit, disabled }: Props) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const fullName = parseRepo(text);
    if (!fullName) {
      setError("Enter a GitHub repository as owner/name or paste its URL.");
      return;
    }
    setError(null);
    onSubmit(fullName);
  }

  function pickExample(repo: string) {
    setText(repo);
    setError(null);
    onSubmit(repo);
  }

  return (
    <form className="repo-form" onSubmit={submit} noValidate>
      <label htmlFor="repo">GitHub repository</label>
      <div className="repo-form__row">
        <input
          id="repo"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="owner/name or https://github.com/owner/name"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error !== null}
          aria-describedby={error ? "repo-error" : undefined}
        />
        <button type="submit" disabled={disabled}>
          Check
        </button>
      </div>
      {error && (
        <p id="repo-error" className="form-error" role="alert">
          {error}
        </p>
      )}
      <p className="examples">
        Try:
        {EXAMPLES.map(({ repo, note }) => (
          <button key={repo} type="button" className="chip" disabled={disabled} onClick={() => pickExample(repo)}>
            {repo} <span className="chip__note">{note}</span>
          </button>
        ))}
      </p>
    </form>
  );
}
