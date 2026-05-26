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
    // to the workspace picker. Like AuthCallback, this is an implicit
    // landing (user just typed the bare root URL), so pass the
    // `autoForwardIfSingle` flag — a single-workspace user gets forwarded
    // straight to /explore instead of seeing a one-card picker. Explicit
    // navigation to /workspaces from the nav does NOT pass the flag and
    // will stay on the page.
    if (window.location.pathname === "/") {
      navigate("/workspaces", {
        replace: true,
        state: { autoForwardIfSingle: true },
      });
    }
  }, [navigate]);

  return <Layout>home</Layout>;
};

export default Home;
