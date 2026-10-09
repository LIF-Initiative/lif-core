
# `frontends/` Directory

This directory houses the **client-facing applications** and tools for interacting with the LIF system. While the core architecture follows a Polylith model centered on Python modules, this directory contains web-based and other frontend clients built using JavaScript, TypeScript, and associated tooling.


## Purpose

The `frontends/` directory exists to support:

- Web interfaces for interacting with LIF services
- Demo UIs or internal tools for visualizing outputs
- Optional external-facing portals or embedded widgets
- Other platform-specific clients (desktop, mobile) if needed

These clients interact with backend services defined in the `components/` and `bases/` directories.

## Tech Stack and Variability

Each subdirectory within `frontends/` can define its own stack and tooling requirements. The structure is intentionally flexible and does not enforce a single frontend framework. Tech choices may include:

- React (with Vite, Tailwind, etc.)
- Vue, Svelte, or other JS frameworks
- Static HTML/JS/CSS apps
- Future support for Electron, Flutter, or mobile web

## Example Structure

<pre lang="markdown"> <code> 
frontends/  
├── lif_advisor_app/      # Web client for the LIF Advisor experience
└── mdr-frontend/         # Web client for the LIF MDR experience
    ├── src/              # React source code
    ├── public/           # Static assets
    ├── Dockerfile        # Optional containerization support
    ├── vite.config.ts    # Vite configuration
    ├── package.json      # JS/TS dependencies
    └── README.md         # App-specific structure, env vars and setup
</code> </pre>


## Usage

Each frontend project includes its own `README.md` and development instructions. 

To run the LIF Advisor frontend locally:
```bash
cd frontends/lif_advisor_app
npm install
npm run dev
```

To run the LIF MDR frontend locally:
```bash
cd frontends/mdr-frontend
npm install
npm run dev
```

## Guidelines for Contributors

-   Keep frontend code isolated within its own subdirectory
-   Use a framework and toolchain suited to the client use case   
-   Define CI, linting, and formatting tools locally (e.g., ESLint, Prettier)   
-   Avoid introducing shared logic between frontend and backend in this directory; use API interfaces to bridge

## Related Directories

-   `components/` — core business logic and services 
-   `bases/` — deployment contexts (e.g. REST APIs, GraphQL)
-   `deployments/` — environment-specific deployment setups
