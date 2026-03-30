import { useState } from "react";
import { startTraining as apiStartTraining, stopTraining as apiStopTraining } from "../api/client";

export type TrainingState = "idle" | "starting" | "running" | "stopping";

export function useTraining(initialState: TrainingState = "idle") {
  const [state, setState] = useState<TrainingState>(initialState);

  const startTraining = async () => {
    setState("starting");
    await apiStartTraining();
    setState("running");
  };

  const stopTraining = async () => {
    setState("stopping");
    await apiStopTraining();
    setState("idle");
  };

  const syncFromServer = (trainingActive: boolean) => {
    setState(trainingActive ? "running" : "idle");
  };

  return { state, setState, startTraining, stopTraining, syncFromServer };
}
