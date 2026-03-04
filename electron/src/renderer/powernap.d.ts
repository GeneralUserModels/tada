/** Global type for the powernap context bridge exposed by preload.ts */

interface PowerNapAPI {
  // Control
  startRecording: () => Promise<unknown>;
  stopRecording: () => Promise<unknown>;
  startTraining: () => Promise<unknown>;
  stopTraining: () => Promise<unknown>;
  startInference: () => Promise<unknown>;
  stopInference: () => Promise<unknown>;
  requestPrediction: () => Promise<unknown>;

  // Status / Settings
  getStatus: () => Promise<unknown>;
  getSettings: () => Promise<unknown>;
  updateSettings: (data: Record<string, unknown>) => Promise<unknown>;
  getTrainingHistory: () => Promise<unknown>;

  // Event listeners (main -> renderer)
  onStatusUpdate: (cb: (data: any) => void) => void;
  onPrediction: (cb: (data: any) => void) => void;
  onScore: (cb: (data: any) => void) => void;
  onElboScore: (cb: (data: any) => void) => void;
  onTrainingStep: (cb: (data: any) => void) => void;
  onLabel: (cb: (data: any) => void) => void;

  onPredictionRequested: (cb: () => void) => void;

  // Overlay-specific
  onOverlayPrediction: (cb: (data: any) => void) => void;
  onOverlayWaiting: (cb: () => void) => void;
  onOverlayFlushing: (cb: () => void) => void;
  onOverlaySleepwalk: (cb: () => void) => void;

  // Overlay resize
  resizeOverlay: (height: number) => void;
}

declare const powernap: PowerNapAPI;
