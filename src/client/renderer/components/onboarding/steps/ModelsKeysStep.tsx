import React from "react";
import { AdvancedLLMSection } from "../../shared/AdvancedLLMSection";
import { ModelDropdown, LLM_MODELS, TINKER_MODELS } from "../../shared/ModelDropdown";

type Props = {
  flag: (name: string) => boolean;
  model: string;
  tinkerModel: string;
  geminiKey: string;
  tinkerKey: string;
  wandbKey: string;
  tinkerError: string;
  advancedValues: Record<string, string>;
  setModel: (v: string) => void;
  setTinkerModel: (v: string) => void;
  setGeminiKey: (v: string) => void;
  setTinkerKey: (v: string) => void;
  setWandbKey: (v: string) => void;
  setAdvancedValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  validateTinker: (v: string) => boolean;
  onBack: () => void;
  onFinish: () => void;
};

export function ModelsKeysStep(props: Props) {
  return (
    <div className="page active">
      <div className="page-icon">
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none"><path d="M4 12V7M8 12V4M12 12V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
      </div>
      <div className="page-title">Models & Keys</div>
      <p className="page-desc">Configure your LLM provider. Uses LiteLLM format — any supported provider works.</p>
      <div className="glass-card">
        <div className="model-row">
          <span className="model-row-label">LLM <span className="required-tag">Required</span></span>
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
              <input type="password" placeholder="AIza..." value={props.geminiKey} onChange={(e) => props.setGeminiKey(e.target.value)}/>
            </div>
          </div>
        </div>
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
        <button className="btn btn-primary" disabled={!props.model.trim() || !props.geminiKey.trim() || (props.flag("tinker") && !!props.tinkerError)} onClick={props.onFinish}>Continue</button>
      </div>
    </div>
  );
}
