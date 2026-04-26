import React, { useEffect, useRef, useState } from "react";

type Props = {
  onBack: () => void;
  onContinue: () => void;
  isFinal?: boolean;
};

type TutorialPage = {
  title: string;
  description: string;
  placeholder: string;
  hint: string;
  // Pre-filled body so the user can immediately press Option+Tab and watch
  // the autocomplete continue from a sensible jumping-off point, instead of
  // staring at a blank box trying to think of something to type.
  initialText?: string;
};

// The textarea here is just a focused playground. The real TabracadabraService
// is already running by the time this step renders (started by the
// getting_ready step), so Option+Tab is captured by the global event tap and
// the response is typed directly into whichever element is focused.
const TUTORIALS: TutorialPage[] = [
  {
    title: "Autocomplete",
    description: "Press Option + Tab to continue text from context.",
    placeholder:
      "Type a few sentences here, then press Option + Tab to keep going.",
    hint: "Tabracadabra picks up where you left off.",
    initialText: "Here's what I've been up to: ",
  },
  {
    title: "You can prompt it too",
    description:
      "Write a question or instruction and press Option + Tab — Tabracadabra responds inline.",
    placeholder:
      "Try: 'rewrite this in pirate speak' or 'summarize the meeting in three bullets'. Then press Option + Tab.",
    hint: "Tabracadabra responds to instructions, not just autocomplete.",
    // Trailing newlines so the textarea reads as a question with the cursor
    // sitting on a fresh line below — visually a prompt, ready for the
    // Option+Tab response to drop right in.
    initialText: "who is gollum? \n\n",
  },
];

export function TabracadabraStep({ onBack, onContinue, isFinal = true }: Props) {
  const [tutorialStep, setTutorialStep] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const tutorial = TUTORIALS[tutorialStep];

  // Reset focus when the user flips between sub-steps so they can keep typing
  // immediately. The textarea is uncontrolled (the real event tap writes to it
  // directly), so we just (re)seed the value and refocus, dropping the cursor
  // at the end so Option+Tab continues from the seed text.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const seed = tutorial.initialText ?? "";
    el.value = seed;
    el.focus();
    const end = seed.length;
    el.setSelectionRange(end, end);
  }, [tutorialStep, tutorial.initialText]);

  const handleBack = () => {
    if (tutorialStep > 0) {
      setTutorialStep(tutorialStep - 1);
    } else {
      onBack();
    }
  };

  const handleNext = () => {
    if (tutorialStep < TUTORIALS.length - 1) {
      setTutorialStep(tutorialStep + 1);
    } else {
      onContinue();
    }
  };

  const isLastTutorial = tutorialStep >= TUTORIALS.length - 1;

  return (
    <div className="page active">
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none">
          <path d="M3 4.5h10M3 8h10M3 11.5h7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
          <path d="M11.2 10.7 13.5 8.4l-2.3-2.3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>
      <div className="page-kicker">Tabracadabra</div>
      <div className="page-title">{tutorial.title}</div>
      <p className="page-desc">{tutorial.description}</p>
      <p className="page-desc" style={{ fontSize: "12px", opacity: 0.5, marginTop: -4 }}>
        {tutorialStep + 1} of {TUTORIALS.length}
      </p>
      <div className="glass-card">
        <div className="field">
          <span className="field-label">Practice prompt</span>
          <textarea
            ref={textareaRef}
            autoFocus
            className="tutorial-box"
            rows={8}
            placeholder={tutorial.placeholder}
            aria-label="Tabracadabra tutorial textbox"
          />
          <span className="field-hint tutorial-hint">{tutorial.hint}</span>
        </div>
      </div>
      <div className="btn-row">
        <button className="btn btn-ghost" onClick={handleBack}>Back</button>
        <button className="btn btn-primary" onClick={handleNext}>
          {!isLastTutorial ? "Next" : isFinal ? "Finish Setup" : "Next"}
        </button>
      </div>
    </div>
  );
}
