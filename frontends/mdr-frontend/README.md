# LIF Metadata Repository (MDR) Frontend

The **Metadata Repository (MDR)** is a key component of LIF. It provides the capabilities to maintain the *LIF data model* in all of its iterations---including an *organization-specific LIF data model* and *partner LIF data models.* The **MDR** and *LIF data model* will be maintained by the steward or organization governing LIF.

The **MDR** is a standalone component that serves as the LIF system of record. It is where individuals from implementing organizations maintain their *organization-specific LIF data model* and *partner LIF data models* through a graphical user interface.

Additionally, the **MDR** provides the capability for the organization to maintain source data model(s) and mappings to transform data into a structure aligned to the *organization-specific LIF data model*.

The **MDR** will enable the organization to define which elements of its *organization-specific LIF data model* can be shared externally as its *partner-accessible LIF data model*. As a Possible Future Roadmap Item, the **MDR** will also allow the retrieval of the *partner-accessible LIF data model* from partners that have allowed for queries via **LIF API**.

# Recommended Setup
```
cd deployments/advisor-demo-docker
docker compose down && docker compose build --no-cache && docker compose up -d
```
To rebuild this component of the stack specifically:
```
cd deployments/advisor-demo-docker
docker compose down lif-mdr-app && docker compose build lif-mdr-app --no-cache && docker compose up lif-mdr-app -d
```

# Setup Instructions
Prerequisites:
- Ensure you have `npm`, `docker`, and `docker-compose` installed.
- Ensure you have spun up the `lif_mdr_api` and `lif_mdr_database` services.

Ports are intentionally varied to validate changes.

Local / Docker Compose:
Start from the lif-main root directory
```
[[default is http://localhost:8012]]
export LIF_MDR_API_URL="http://localhost:8099"
docker-compose -f deployments/advisor-demo-docker/docker-compose.yml up --build
```

Local / Docker:
Start from the lif-main frontends/mdr-frontend directory
```
docker build --build-arg LIF_MDR_API_URL=http://localhost:8055 -t mdr-frontend:latest .
docker run -p 9000:80 mdr-frontend:latest
```

Local / Native:
Default MDR frontend URL is http://localhost:5173.
```
npm install
export VITE_API_URL=http://localhost:8099
npm run dev
```

Tests (vitest):
```
npm install
npm test
```
