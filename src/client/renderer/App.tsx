import React from "react";
import { useAppContext } from "./context/AppContext";
import { useFeatureFlag } from "./featureFlags";
import { Sidebar } from "./components/Sidebar";
import { ActivityLogView } from "./components/views/ActivityLogView";
import { UserModelView } from "./components/views/UserModelView";
import { SettingsView } from "./components/views/SettingsView";
import { TadaView } from "./components/views/TadaView";
import { MemexView } from "./components/views/MemexView";
import { SeekerView } from "./components/views/SeekerView";
import { UpdateBanner } from "./components/UpdateBanner";

export function App() {
  const { state, dispatch } = useAppContext();
  const momentsEnabled = useFeatureFlag("moments");
  const memoryEnabled = useFeatureFlag("memory");
  const seekerEnabled = useFeatureFlag("seeker");

  const navigate = (view: typeof state.activeView) => {
    dispatch({ type: "NAVIGATE", view });
  };

  return (
    <>
    <div className="drag-topbar" />
    <div id="app">
      <Sidebar
        activeView={state.activeView}
        connected={state.connected}
        agentActivities={state.agentActivities}
        onNavigate={navigate}
      />
      <main id="content">
        {state.updateVersion && (
          <UpdateBanner
            version={state.updateVersion}
            progress={state.updateProgress}
            ready={state.updateReady}
            installing={state.updateInstalling}
            error={state.updateError}
            onInstall={() => dispatch({ type: "UPDATE_INSTALLING" })}
            onDismiss={() => dispatch({ type: "UPDATE_DISMISSED" })}
          />
        )}
        {state.activeView === "activity" && <ActivityLogView />}
        {state.activeView === "tada" && momentsEnabled && <TadaView />}
        {state.activeView === "memex" && memoryEnabled && <MemexView />}
        {state.activeView === "seeker" && seekerEnabled && <SeekerView />}
        {state.activeView === "usermodel" && <UserModelView />}
        {state.activeView === "settings" && <SettingsView />}
      </main>
    </div>
    </>
  );
}
