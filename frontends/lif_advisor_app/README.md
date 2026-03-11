# Introduction 
The LIF Advisor App is a sample nodejs/react based frontend application for the LIF framework.

# Getting Started

## Hosting

### Environment Variables

example environment file

```bash
VITE_LIF_ADVISOR_API_URL=http://localhost:8004
```

## Local Development

### Initial setup
1.  Install Node JS, version 20
    - See: https://nodejs.org/en/download
    - Verify:
      - in a terminal, run:
          ```
          node --version
          ```
      - you should see "v20" and some additional numbers printed
2.  Install NPM dependencies
    - Instructions: in a terminal, run:
        ```
        npm install 
        ```
    - Verify:
      - in a terminal, run:
          ```
          cd node_modules
          ```
      - then run:
          ```
          ls
          ```
      - you should see a list of folders which are the project dependencies

### Starting a development server

This runs the application and automatically refreshes the browser as you change local files.

1.  setup the environment variables, see [the environment section above](#environment-variables)
2.  in a terminal, run:
    ```
    npm run dev
    ```
3.  open a web browser and visit <http://localhost:5174>

### Docker

1. Build the Docker image
    ``` shell
    docker build -t lif_advisor_app -f docker/Dockerfile --build-arg=LIF_MCP_AGENT_URL=http://localhost:8004 --no-cache .
    ```
2. Run the image
    ``` shell
    docker run -d --name lif_advisor_app -p 5174:80 lif_advisor_app
    ```

The web application can then be accessed at http://localhost:5174
