# AI Agent and Tool Implementation Pattern Handout

One-page handout on using LIF to give AI agents and tools rich learner context and persistent, shared memory.

## I. Use Case Description

- **Summary use case value prop** – Use LIF to provide rich context about individual learners and persistent, shareable memory to power AI agents and other AI tools.
- **Value for learners** – LIF-powered AI agents leverage a learner's academic, employment, skills, and aspiration data to deliver personalized information and advice from the first interaction—eliminating the need for learners to provide that context for each interaction and making the agent immediately useful. Learners can also update their learner data by providing new information (e.g., latest career aspirations) so agents can keep pace with learners' evolving goals.
- **Value for implementing organizations** – Using LIF to power AI agents and other AI tools unlocks value and insights from existing data sources, making investments in AI tools more impactful in improving learner experiences and outcomes. LIF can also provide shared, persistent memory across all of the organization's AI tools supporting learners, saving the time and frustration of repeated context-setting AI tools require to be effective.
- **Value for builders** – LIF delivers the rich learner context and persistent, shared memory that AI tools require to support relevant and impactful interactions with learners, reducing the risks of undermining trust and eroding engagement. The core LIF tool set also includes a standard MCP interface for AI tools, so developers need not create custom interfaces to enable their tools to access LIF-formatted data.
- **Value to partners & networks** – LIF enables organizations to draw on data at authorized partner organizations to enrich learner context and make it portable across organizations throughout a learner's journey. The portability of rich learner context allows the AI tools of partner organizations to benefit from access to a more holistic, longitudinal view of the learner that will improve personalization and foster engagement.

## II. Use Case Data Flows and LIF's Role(s) in Facilitating Them

![Data flow diagram for the AI agent use case. A learner interacts with the LIF Advisor Agent and other AI tools (LIF Clients, in the Application Provider). These connect to the LIF MCP Server, which calls the LIF API. The LIF API works with the MDR and the LIF middleware components, which retrieve data from source systems and from a partner organization's LIF API Gateway, and write new learner information back to source systems.](../media/image_aiAgentPattern_1.png)

## III. LIF vs. another solution

- Many AI tools today cannot access the necessary context for relevant interactions with learners. This can lead to insufficient personalization and irrelevant guidance. The only means for addressing these challenges is to have the learner provide the context for each interaction, which can burdensome and frustrating.
- Without LIF and the MCP Server, implementors must build a unique read-write interface with multiple source and remote systems for each AI tool.

## IV. What is in-scope vs. out-of-scope for LIF

- LIF assumes that AI tools are running in a trusted and secure environment, and each tool is responsible for authentication and authorization.
- It is possible to extend that functionality into the MCP Server and LIF API if needed in the future, but LIF does not currently have that functionality.

## Example of Prototype LIF Advisor Agent Leveraging Rich Context to Support Learner

![Screenshot of the prototype LIF Advisor chat. A learner asks for a summary of their proficiencies related to risk management, and the advisor replies with a bulleted summary drawn from the learner's skills, experience, and academic credentials, followed by suggested next-step buttons.](../media/image_aiAgentPattern_2.png)
