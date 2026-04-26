import React, { useState } from "react";
import { buildChatSampleHtml, type ChatSampleConfig } from "./chatSample";

type Props = {
  onBack: () => void;
  onContinue: () => void;
  isFinal?: boolean;
};

interface ChatTutorial extends ChatSampleConfig {
  label: string;
  hint: string;
}

const TUTORIALS: ChatTutorial[] = [
  {
    label: "Today's inbox",
    hint: "Newsletters and known noise are filtered automatically.",
    sessionTitle: "Today's emails",
    userPrompt: "Summarize my important emails from today",
    assistantHtml: [
      "Three worth a look today.",
      '<div class="row"><span class="who">Glinda</span><span class="when">9:14 AM</span></div>',
      '<div class="body">Confirms <strong>3pm tomorrow at the Emerald Palace</strong>. <em>Reply needed before sundown.</em></div>',
      '<div class="row"><span class="who">Tin Man</span><span class="when">11:42 AM</span></div>',
      '<div class="body">Wants sign-off on the Quadling vendor switch by Thursday.</div>',
      '<div class="row"><span class="who">Lion</span><span class="when">1:03 PM</span></div>',
      '<div class="body">Thanks for the pep talk. No reply needed.</div>',
      '<div class="footer">Skipped 14 newsletters and 2 from the West Witch.</div>',
    ].join(""),
  },
  {
    label: "Meeting prep",
    hint: "Works for any name on your calendar.",
    sessionTitle: "Glinda · 3pm prep",
    userPrompt: "Prep me for my 3pm with Glinda tomorrow",
    assistantHtml: [
      "Quick brief from your last threads with her.",
      '<div class="row"><span class="who">Last meeting</span><span class="when">Mar 12</span></div>',
      '<div class="body">You agreed to test the southern route. <em>Check-in is still open.</em></div>',
      '<div class="row"><span class="who">Open threads</span><span class="when"></span></div>',
      '<div class="body"><ul><li>Flying-monkey patrol dates</li><li>Inviting Scarecrow to the route review</li></ul></div>',
      '<div class="row"><span class="who">Worth flagging</span><span class="when"></span></div>',
      '<div class="body">She mentioned the West Witch\'s silence. You haven\'t followed up.</div>',
      '<div class="footer">Pulled from 3 emails and 1 calendar note.</div>',
    ].join(""),
  },
];

export function ChatStep({ onBack, onContinue, isFinal = false }: Props) {
  const [tutorialStep, setTutorialStep] = useState(0);
  const tutorial = TUTORIALS[tutorialStep];
  const isLast = tutorialStep === TUTORIALS.length - 1;

  const handleBack = () => {
    if (tutorialStep > 0) setTutorialStep(tutorialStep - 1);
    else onBack();
  };

  const handleNext = () => {
    if (!isLast) setTutorialStep(tutorialStep + 1);
    else onContinue();
  };

  return (
    <div className="page active" style={{ maxWidth: 480 }}>
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none">
          <path
            d="M2.5 4.5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v4.5a2 2 0 0 1-2 2H7l-2.8 2.2v-2.2H4.5a2 2 0 0 1-2-2v-4.5z"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinejoin="round"
          />
          <circle cx="6" cy="6.8" r="0.7" fill="currentColor" />
          <circle cx="8" cy="6.8" r="0.7" fill="currentColor" />
          <circle cx="10" cy="6.8" r="0.7" fill="currentColor" />
        </svg>
      </div>
      <div className="page-kicker">Chat</div>
      <div className="page-title">Ask anything</div>
      <p className="page-desc">
        Answers personalized with everything Tada sees. Two examples below.
      </p>
      <p
        className="page-desc"
        style={{ fontSize: "11px", opacity: 0.55, marginTop: -6, marginBottom: 8 }}
      >
        Example {tutorialStep + 1} of {TUTORIALS.length} · {tutorial.label}
      </p>

      <iframe
        key={tutorialStep}
        className="sample-iframe"
        sandbox="allow-scripts"
        srcDoc={buildChatSampleHtml(tutorial)}
        title={`Sample chat: ${tutorial.label}`}
        style={{ height: 300 }}
      />

      <p className="sample-hint">{tutorial.hint}</p>

      <div className="btn-row">
        <button className="btn btn-ghost" onClick={handleBack}>Back</button>
        <button className="btn btn-primary" onClick={handleNext}>
          {!isLast ? "Next" : isFinal ? "Finish Setup" : "Next"}
        </button>
      </div>
    </div>
  );
}
