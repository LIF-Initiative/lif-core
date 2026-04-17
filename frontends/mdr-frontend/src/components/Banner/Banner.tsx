import React, { useState, useEffect } from "react";
import { Button, Flex, Text } from "@radix-ui/themes";
import { CopyIcon, Cross1Icon } from "@radix-ui/react-icons";
import { useAuth } from "../../context/AuthContext";
import "./Banner.css";

interface BannerProps {
  name: string;
  content: React.ReactNode;
  copyText?: string;
  copyRichText?: string;
}

const Banner: React.FC<BannerProps> = ({ name, content, copyText, copyRichText }) => {
  name = name || "default";
  copyRichText = copyRichText || "";
  copyText = copyText || stripHtml(copyRichText) || "";

  const { user } = useAuth();
  const [isVisible, setIsVisible] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);

  function stripHtml(html: string) {
    const temporalDivElement = document.createElement("div"); 
    temporalDivElement.innerHTML = html;
    return temporalDivElement.textContent || temporalDivElement.innerText || ""; 
  }

  // Check if banner should be shown
  useEffect(() => {
    if (user) {
      const bannerDismissed = localStorage.getItem(`banner-${name}-${user.email || 'user'}`) === 'true';
      if (!bannerDismissed) {
        setIsVisible(true);
      }
    }
  }, [user, name]);

  const handleDismiss = () => {
    setIsVisible(false);
    if (user) {
      localStorage.setItem(`banner-${name}-${user.email || 'user'}`, 'true');
    }
  };

  const handleCopy = async () => {
    if (!copyText) return;

    try {
      if (copyRichText) {
        const clipboardItem = new ClipboardItem({
          'text/html': new Blob([copyRichText], { type: 'text/html' }),
          'text/plain': new Blob([copyText || ''], { type: 'text/plain' })
        });
        await navigator.clipboard.write([clipboardItem]);
      } else {
        await navigator.clipboard.writeText(copyText);
      }
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
      // Final fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = copyText || "";
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      handleDismiss();
    }
  };

  if (!isVisible) {
    return null;
  }

  return (
    <div 
      className="banner"
      role="banner"
      aria-label="Important notification"
      onKeyDown={handleKeyDown}
    >
      <Flex className="banner-content" align="center" gap="3">
        <div className="banner-text" aria-live="polite">
          {content}
        </div>
        
        <Flex className="banner-actions" align="center" gap="2">
          {(copyText || copyRichText) && (
            <Button
              variant="soft"
              size="1"
              className="banner-copy-button"
              onClick={handleCopy}
              aria-label={copySuccess ? "Text copied to clipboard" : "Copy text to clipboard"}
              title={copySuccess ? "Copied!" : "Copy to clipboard"}
            >
              <CopyIcon />
              {copySuccess && <span className="copy-success-text">Copied!</span>}
            </Button>
          )}
          
          <Button
            variant="ghost"
            size="1"
            className="banner-close-button"
            onClick={handleDismiss}
            aria-label="Dismiss notification"
            title="Dismiss"
          >
            <Cross1Icon />
          </Button>
        </Flex>
      </Flex>
    </div>
  );
};

export default Banner;