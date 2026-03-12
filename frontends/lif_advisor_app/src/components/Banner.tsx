import React, { useState, useEffect } from "react";
import { Copy, X } from "lucide-react";
import { UserDetails } from "../types";

interface BannerProps {
  content: React.ReactNode;
  copyText?: string;
  user: UserDetails | null;
}

const Banner: React.FC<BannerProps> = ({ content, copyText, user }) => {
  const [isVisible, setIsVisible] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);

  // Check if banner should be shown
  useEffect(() => {
    if (user && user.username) {
      const storageKey = `banner-citation-${user.username}`;
      const bannerDismissed = localStorage.getItem(storageKey);
      
      if (!bannerDismissed) {
        setIsVisible(true);
      } else {
        setIsVisible(false);
      }
    }
  }, [user]);

  const handleDismiss = () => {
    setIsVisible(false);
    if (user && user.username) {
      const storageKey = `banner-citation-${user.username}`;
      localStorage.setItem(storageKey, 'true');
    }
  };

  const handleCopy = async () => {
    if (!copyText) return;

    try {
      await navigator.clipboard.writeText(copyText);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = copyText;
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
      className="sticky top-0 bg-blue-50 border-b border-blue-200 text-gray-700 px-4 py-3 relative w-full z-50"
      role="banner"
      aria-label="Important notification"
      onKeyDown={handleKeyDown}
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        <div className="flex-1 text-sm leading-relaxed" aria-live="polite">
          {content}
        </div>
        
        <div className="flex items-center gap-2 flex-shrink-0">
          {copyText && (
            <button
              className="inline-flex items-center justify-center p-1.5 rounded-md text-gray-700 hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-colors relative"
              onClick={handleCopy}
              aria-label={copySuccess ? "Text copied to clipboard" : "Copy text to clipboard"}
              title={copySuccess ? "Copied!" : "Copy to clipboard"}
            >
              <Copy size={16} />
              {copySuccess && (
                <span className="absolute left-full ml-2 bg-green-600 text-white px-2 py-1 rounded text-xs whitespace-nowrap animate-fade-in-out">
                  Copied!
                </span>
              )}
            </button>
          )}
          
          <button
            className="inline-flex items-center justify-center p-1.5 rounded-md text-black hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-colors"
            onClick={handleDismiss}
            aria-label="Dismiss notification"
            title="Dismiss"
          >
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};


export default Banner;