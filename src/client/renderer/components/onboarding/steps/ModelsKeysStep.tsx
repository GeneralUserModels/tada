/// <reference path="../../../tada.d.ts" />
import React from "react";
import { AdvancedLLMSection } from "../../shared/AdvancedLLMSection";
import { ModelDropdown, LLM_MODELS, AGENT_MODELS, TINKER_MODELS } from "../../shared/ModelDropdown";

const GOOGLE_AI_STUDIO_API_KEY_URL = "https://aistudio.google.com/app/apikey";
const ANTHROPIC_API_KEY_URL = "https://console.anthropic.com/settings/keys";
const GOOGLE_ZDR_URL = "https://cloud.google.com/vertex-ai/generative-ai/docs/vertex-ai-zero-data-retention";
const ANTHROPIC_ZDR_URL = "https://platform.claude.com/docs/en/build-with-claude/zero-data-retention";

type Props = {
  flag: (name: string) => boolean;
  model: string;
  agentModel: string;
  tinkerModel: string;
  labelerKey: string;
  agentKey: string;
  tinkerKey: string;
  wandbKey: string;
  tinkerError: string;
  advancedValues: Record<string, string>;
  setModel: (v: string) => void;
  setAgentModel: (v: string) => void;
  setTinkerModel: (v: string) => void;
  setLabelerKey: (v: string) => void;
  setAgentKey: (v: string) => void;
  setTinkerKey: (v: string) => void;
  setWandbKey: (v: string) => void;
  setAdvancedValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  validateTinker: (v: string) => boolean;
  onBack: () => void;
  onFinish: () => void;
};

export function ModelsKeysStep(props: Props) {
  const openGoogleApiKeyPage = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    void window.tada.openExternalUrl(GOOGLE_AI_STUDIO_API_KEY_URL);
  };
  const openAnthropicApiKeyPage = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    void window.tada.openExternalUrl(ANTHROPIC_API_KEY_URL);
  };
  const openGoogleZdrPage = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    void window.tada.openExternalUrl(GOOGLE_ZDR_URL);
  };
  const openAnthropicZdrPage = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    void window.tada.openExternalUrl(ANTHROPIC_ZDR_URL);
  };
  const agentLmNeeded =
    props.flag("moments") || props.flag("memory") || props.flag("seeker");

  return (
    <div className="page active page--scroll">
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none"><path d="M4 12V7M8 12V4M12 12V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
      </div>
      <div className="page-title">Models & Keys</div>
      <p className="page-desc">Configure your LLM providers. Uses LiteLLM format — any supported provider works.</p>
      <div className="glass-card">
        <div className="model-row">
          <span className="model-row-label">Labeling LM <span className="required-tag">Required</span></span>
          <div className="model-row-fields">
            <div className="field">
              <span>Model</span>
              <ModelDropdown
                value={props.model}
                onChange={props.setModel}
                options={LLM_MODELS}
                placeholder="Select a model"
              />
            </div>
            <div className="field">
              <span>API Key</span>
              <input type="password" placeholder="AIza..." value={props.labelerKey} onChange={(e) => props.setLabelerKey(e.target.value)}/>
            </div>
          </div>
          <p className="onboarding-api-key-hint">
            You can get your key at{" "}
            <a href={GOOGLE_AI_STUDIO_API_KEY_URL} onClick={openGoogleApiKeyPage}>
              Google AI Studio
            </a>
            {" "}. Make sure your account is upgraded from the free tier so you don't run into rate limits. For sensitive data, consider setting up{" "}
            <a href={GOOGLE_ZDR_URL} onClick={openGoogleZdrPage}>
              Zero Data Retention on Vertex AI
            </a>
            .
          </p>
        </div>
        {agentLmNeeded && (
          <div className="model-row">
            <span className="model-row-label">Agent LM <span className="required-tag">Required</span></span>
            <div className="model-row-fields">
              <div className="field">
                <span>Model</span>
                <ModelDropdown
                  value={props.agentModel}
                  onChange={props.setAgentModel}
                  options={AGENT_MODELS}
                  placeholder="Select a model"
                />
              </div>
              <div className="field">
                <span>API Key</span>
                <input type="password" placeholder="sk-ant-..." value={props.agentKey} onChange={(e) => props.setAgentKey(e.target.value)}/>
              </div>
            </div>
            <p className="onboarding-api-key-hint">
              You can get your key at{" "}
              <a href={ANTHROPIC_API_KEY_URL} onClick={openAnthropicApiKeyPage}>
                Anthropic Console
              </a>
              {" "}. Make sure your account is upgraded from the free tier so you don't run into rate limits. For sensitive data, consider requesting{" "}
              <a href={ANTHROPIC_ZDR_URL} onClick={openAnthropicZdrPage}>
                Zero Data Retention
              </a>
              {" "}from your Anthropic account team.
            </p>
          </div>
        )}
        <AdvancedLLMSection values={props.advancedValues} setValues={props.setAdvancedValues} />
        {props.flag("tinker") && (
          <div className="model-row">
            <span className="model-row-label">Tinker <span className="optional-tag">optional</span></span>
            <div className="model-row-fields">
              <div className="field">
                <span>Model</span>
                <ModelDropdown value={props.tinkerModel} onChange={props.setTinkerModel} options={TINKER_MODELS} placeholder="Select a model" />
              </div>
              <div className="field">
                <span>API Key</span>
                <input type="password" placeholder="tml-..." value={props.tinkerKey}
                  onChange={(e) => { props.setTinkerKey(e.target.value); props.validateTinker(e.target.value); }}/>
                {props.tinkerError && <span className="field-hint" style={{ color: "var(--danger)" }}>{props.tinkerError}</span>}
              </div>
            </div>
          </div>
        )}
        <div className="model-row">
          <span className="model-row-label">W&amp;B <span className="optional-tag">optional</span></span>
          <div className="model-row-fields">
            <div className="field">
              <span>API Key</span>
              <input type="password" placeholder="wandb-..." value={props.wandbKey} onChange={(e) => props.setWandbKey(e.target.value)}/>
            </div>
            <div className="field"></div>
          </div>
        </div>
      </div>
      <div className="btn-row">
        <button className="btn btn-ghost" onClick={props.onBack}>Back</button>
        <button className="btn btn-primary" disabled={!props.model.trim() || !props.labelerKey.trim() || (agentLmNeeded && (!props.agentModel.trim() || !props.agentKey.trim())) || (props.flag("tinker") && !!props.tinkerError)} onClick={props.onFinish}>Continue</button>
      </div>
    </div>
  );
}
