"use client";

import { useState } from "react";
import { api } from "@/lib/api/client";
import type { FeedbackRating } from "@/lib/api/types";

type Status = "idle" | "sending" | "sent" | "error";

/** "Was this useful?" for a whole answer or assessment, with an optional comment on "No". */
export function FeedbackBar({ responseId, subject }: { responseId: string; subject: string }) {
  const [status, setStatus] = useState<Status>("idle");
  const [rating, setRating] = useState<FeedbackRating | null>(null);
  const [comment, setComment] = useState("");

  async function send(r: FeedbackRating, text?: string) {
    setStatus("sending");
    try {
      await api.feedback({ responseId, rating: r, comment: text || undefined });
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  }

  if (status === "sent") return <p className="text-xs text-muted">Thanks, your feedback was recorded.</p>;
  const btn = "rounded-md border border-line px-3 py-1 text-xs hover:bg-subtle disabled:opacity-50";
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
      <span>Was this {subject} useful?</span>
      <button className={btn} disabled={status === "sending"} onClick={() => send("useful")}>
        Yes
      </button>
      <button className={btn} disabled={status === "sending"} onClick={() => setRating("not_useful")}>
        No
      </button>
      {rating === "not_useful" && (
        <form
          className="flex w-full gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send("not_useful", comment);
          }}
        >
          <input
            className="min-w-0 flex-1 rounded-md border border-line bg-background px-2 py-1"
            placeholder="What was wrong? (optional)"
            maxLength={1000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <button className={btn} disabled={status === "sending"} type="submit">
            Send
          </button>
        </form>
      )}
      {status === "error" && <span className="text-risk-high">Could not send feedback; please try again.</span>}
    </div>
  );
}

/** Flag one citation as not supporting what it is cited for. */
export function FlagCitation({ responseId, citationId }: { responseId: string; citationId: string }) {
  const [status, setStatus] = useState<Status>("idle");
  if (status === "sent") return <span>flagged, thanks</span>;
  return (
    <button
      className="text-muted underline-offset-2 hover:text-risk-high hover:underline disabled:opacity-50"
      disabled={status === "sending"}
      title="This passage does not support what it is cited for"
      onClick={async () => {
        setStatus("sending");
        try {
          await api.feedback({ responseId, rating: "bad_citation", citationId });
          setStatus("sent");
        } catch {
          setStatus("error");
        }
      }}
    >
      {status === "error" ? "flag failed, retry" : "flag citation"}
    </button>
  );
}
