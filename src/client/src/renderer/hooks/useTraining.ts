import { useState } from "react";

export type TrainingState = "idle" | "starting" | "running" | "stopping";

export function useTraining(initialState: TrainingState = "idle") {
  const [state, setState] = useState<TrainingState>(initialState);

  const startTraining = async () => {
    setState("starting");
    await window.powernap.startTraining();
    setState("running");
  };

  const stopTraining = async () => {
    setState("stopping");
    await window.powernap.stopTraining();
    setState("idle");
  };

  const syncFromServer = (trainingActive: boolean) => {
    setState(trainingActive ? "running" : "idle");
  };

  return { state, setState, startTraining, stopTraining, syncFromServer };
}
