# LIF Load Testing

Date: 2025-09-30

## Status  
Accepted

---

## Context

The project involves building and maintaining a suite of services that expose **GraphQL** APIs. There is a need to simulate realistic user loads in order to establish accurate performance baselines. The chosen solution must support modern protocols, including **GraphQL queries and mutations**, and provide readable, maintainable, and version-controllable test definitions. Additionally, the approach should be developer-friendly and complement the existing tech stack for automated testing, which includes Playwright and Typescript.

---

## Decision

We have selected **k6** as the primary tool for load and performance testing.

### Justification:
- **Excellent support for REST and GraphQL APIs** including posting queries with variables
- **JavaScript-based scripting** fits our developer skillset and promotes readable and version-controlled tests
- **Lightweight and CLI-driven**, making it easy to integrate into GitHub Actions and CI/CD pipelines
- **Active open-source project backed by Grafana Labs**, with growing ecosystem and observability integration (e.g., output to Grafana, InfluxDB, etc.)
- Built-in **modular architecture** with extensibility via `xk6` for advanced protocols (e.g., WebSockets for GraphQL subscriptions)

---

## Alternatives

| Tool       | REST Support | GraphQL Support | Ease of Use       | Maintenance / Ecosystem | Tradeoffs / Notes |
|------------|--------------|-----------------|--------------------|---------------------------|-------------------|
| **JMeter** | ✅ Excellent | ⚠️ Good (recent support via samplers) | 🟡 Moderate (GUI-based, complex for advanced logic) | ✅ Very active, large community | GUI helps beginners; advanced logic is cumbersome; legacy feel |
| **Locust** | ✅ Excellent | 🟡 Decent (via plugins or manual scripting) | ✅ High (Python-based, very flexible) | ✅ Active, but plugin support varies | Great for Python teams; advanced GraphQL needs effort |
| **Gatling**| ✅ Strong    | ⚠️ Partial (no built-in GraphQL helpers) | 🟡 Moderate (Scala/Java DSL) | ✅ Maintained; commercial support | High performance; steeper learning for non-Java teams |
| **Artillery** | ✅ Good    | ✅ Good (supports queries, mutations, WebSockets) | ✅ High (YAML + JS, quick start) | 🟡 Maintained; smaller community | Great for modern stacks; limited advanced analytics |

---

## Consequences

**Positive:**
- Faster onboarding and adoption by developers due to JS-based scripting
- Easy CI/CD integration improves automation and test coverage
- Ability to reuse and version performance test cases alongside application code
- Flexibility to extend protocol support via `xk6`

**Negative/Trade-offs:**
- No built-in GUI for test design (may be a learning curve for QA engineers used to visual tools)
- Large-scale distributed testing may require custom setup or paid cloud version (k6 Cloud)
- Some advanced GraphQL features (e.g., persisted queries or subscriptions) may require manual scripting or extensions

---

## References

- [k6 Documentation](https://k6.io/docs/)
- [xk6 Extensions](https://github.com/grafana/xk6)
- [Load Testing GraphQL with k6](https://k6.io/docs/using-k6/guides/graphql-testing/)
- [Internal Evaluation Report – Load Testing Tools](internal-link-if-applicable)
