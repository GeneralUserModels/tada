import { useAppContext } from "./context/AppContext";
import { Sidebar } from "./components/Sidebar";
import { ConnectorsView } from "./components/views/ConnectorsView";
import { UserModelView } from "./components/views/UserModelView";
import { SettingsView } from "./components/views/SettingsView";
import { UpdateModal } from "./components/modals/UpdateModal";

export function App() {
  const { state, dispatch } = useAppContext();

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
        onNavigate={navigate}
      />
      <main id="content">
        {state.updateVersion && (
          <UpdateModal
            version={state.updateVersion}
            onDismiss={() => dispatch({ type: "UPDATE_DISMISSED" })}
          />
        )}
        {state.activeView === "connectors" && <ConnectorsView />}
        {state.activeView === "usermodel" && <UserModelView />}
        {state.activeView === "settings" && <SettingsView />}
      </main>
    </div>
    </>
  );
}
