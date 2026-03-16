import ReactDOM from "react-dom/client";
import { Theme } from "@radix-ui/themes";
import { RouterProvider } from "react-router-dom";
import { MdrProvider } from "./context/MdrContext";
import { AuthProvider } from "./context/AuthContext";
import router from "./pages/Routes";
import "./utils/analytics";
import "./index.css";
import "@radix-ui/themes/styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
    <Theme className="theme-root">
        <AuthProvider>
          <MdrProvider>
            <RouterProvider router={router} />
          </MdrProvider>
        </AuthProvider>
    </Theme>
);
