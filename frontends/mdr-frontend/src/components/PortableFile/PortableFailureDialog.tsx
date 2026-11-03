import React from "react";
import { Button, Dialog, Flex } from "@radix-ui/themes";
import RefusalList from "@/components/RefusalList/RefusalList";
import type { PortableFailure } from "@/services/portableService";

export interface PortableFailureDialogProps {
  title: string;
  failure: PortableFailure | null;
  action: "import" | "export";
  onClose: () => void;
}

/** Why a portable export or import failed, with every refusal. Open while failure is set. */
const PortableFailureDialog: React.FC<PortableFailureDialogProps> = ({ title, failure, action, onClose }) => (
  <Dialog.Root open={!!failure} onOpenChange={(open) => { if (!open) onClose(); }}>
    <Dialog.Content maxWidth="800px" style={{ maxHeight: "85vh", overflow: "auto" }}>
      <Dialog.Title>{title}</Dialog.Title>
      <Dialog.Description size="2" mb="3">
        {failure?.kind === "refused" ? "Each reason names the element it concerns." : "The request failed."}
      </Dialog.Description>
      {failure && <RefusalList failure={failure} action={action} />}
      <Flex gap="3" mt="4" justify="end">
        <Button onClick={onClose}>OK</Button>
      </Flex>
    </Dialog.Content>
  </Dialog.Root>
);

export default PortableFailureDialog;
