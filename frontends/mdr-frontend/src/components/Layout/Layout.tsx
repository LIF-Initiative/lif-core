import React from "react";
// import "./Layout.css";
import { Outlet, useLocation } from "react-router-dom";
import Header from "../Header/Header";
import Footer from "../Footer/Footer";
import Banner from "../Banner/Banner";
import { RouterWrapper } from "../RouterWrapper";
import { Flex } from "@radix-ui/themes";

const Layout: React.FC<any> = ({ children }) => {
  const location = useLocation();

  // Sample banner content with HTML and links
  const bannerContent = (
    <>
      Need to cite this project? Visit{" "}
      <a href="https://github.com/LIF-Initiative/lif-core" target="_blank" rel="noopener noreferrer">
        https://github.com/LIF-Initiative/lif-core
      </a>{" "}
      or click the copy button to grab the citation.
    </>
  );
  // Text to be copied when copy button is clicked
  const copyText = "LIF Initiative. (2026). LIF Core: Core framework of LIF components [Computer software]. GitHub. https://github.com/LIF-Initiative/lif-core";

  return (
    <RouterWrapper>
      <Flex direction={"column"} className="app-container">
        <Banner content={bannerContent} copyText={copyText} />
        <Header />
        <main className="app-main">
          {location.pathname === "/" ? children : <Outlet />}
        </main>
        <Footer />
      </Flex>
    </RouterWrapper>
  );
};

export default Layout;
