import { useAppContext } from "./context/AppContext";
import { Sidebar } from "./components/Sidebar";
import { ConnectorsView } from "./components/views/ConnectorsView";
import { SettingsView } from "./components/views/SettingsView";
import { UpdateModal } from "./components/modals/UpdateModal";
import { PermissionModal } from "./components/modals/PermissionModal";

export function App() {
  const { state, dispatch } = useAppContext();

  const navigate = (view: typeof state.activeView) => {
    dispatch({ type: "NAVIGATE", view });
  };

  return (
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
        {state.permModal && (
          <PermissionModal
            connectorName={state.permModal.connectorName}
            onClose={() => dispatch({ type: "CLOSE_PERM_MODAL" })}
          />
        )}
        {state.activeView === "connectors" && <ConnectorsView />}
        {state.activeView === "settings" && <SettingsView />}
      </main>
    </div>
  );
}
