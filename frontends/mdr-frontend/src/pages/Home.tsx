import React from "react";
// import MainContent from "../components/MainContent/MainContent";
import Layout from "../components/Layout/Layout";
import { useNavigate } from "react-router-dom";

const Home: React.FC = () => {
  const navigate = useNavigate();
  const navigateToLifModelPage = () => {
    navigate("/explore/lif-model");
  };

  React.useEffect(() => {
    // Until we have a real home page, send a logged-in user landing on /
    // to the workspace picker. The Workspaces page itself auto-forwards to
    // /explore when the user has exactly one workspace, so this is mostly
    // a brief loading screen for single-group users (the common case).
    if (window.location.pathname === "/") {
      navigate("/workspaces", { replace: true });
    }
  }, [navigate]);

  return <Layout>home</Layout>;
};

export default Home;
