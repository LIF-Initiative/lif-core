import React from "react";
import { Code, Text } from "@radix-ui/themes";
import type { PortableFailure } from "@/services/portableService";

export interface RefusalListProps {
  failure: PortableFailure;
  action: "import" | "export";
}

/** Every reason the MDR API refused a portable file, or its one message. */
const RefusalList: React.FC<RefusalListProps> = ({ failure, action }) => {
  if (failure.kind === "message") {
    return <Text color="red" size="2" style={{ whiteSpace: "pre-line" }}>{failure.message}</Text>;
  }
  const reasons = `${failure.refusals.length} reason${failure.refusals.length === 1 ? "" : "s"}`;
  // 409: every refusal is a create-only conflict, so the file is fine and its content is already installed.
  const summary = action === "export"
    ? `This can't be exported as a portable file, for ${reasons}:`
    : failure.status === 409
      ? "This content is already installed. Nothing was imported:"
      : `The file was refused for ${reasons}. Nothing was imported:`;
  return (
    <div>
      <Text as="p" color="red" size="2" mb="2">{summary}</Text>
      <ul style={{ margin: 0, paddingLeft: "1.25rem" }}>
        {failure.refusals.map((refusal, index) => (
          <li key={index}>
            <Text size="2">
              <Code>{refusal.code}</Code>
              {refusal.element && <> at <Code variant="ghost">{refusal.element}</Code></>}: {refusal.reason}
            </Text>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default RefusalList;
