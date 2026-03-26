import React, { createContext, useContext, ReactNode } from 'react';
import * as Toast from '@radix-ui/react-toast';
import { Cross2Icon } from '@radix-ui/react-icons';

interface ToastContextType {
  showToast: (message: string, type?: 'success' | 'error' | 'warning' | 'info') => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

interface ToastProviderProps {
  children: ReactNode;
}

export const ToastProvider: React.FC<ToastProviderProps> = ({ children }) => {
  const [toasts, setToasts] = React.useState<Array<{
    id: string;
    message: string;
    type: 'success' | 'error' | 'warning' | 'info';
  }>>([]);

  const showToast = (message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info') => {
    const id = Math.random().toString(36).substr(2, 9);
    setToasts(prev => [...prev, { id, message, type }]);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      setToasts(prev => prev.filter(toast => toast.id !== id));
    }, 5000);
  };

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(toast => toast.id !== id));
  };

  const getToastStyles = (type: string) => {
    const baseStyles = {
      backgroundColor: 'white',
      border: '2px solid',
      borderRadius: '6px',
      padding: '15px',
      display: 'grid',
      gridTemplateAreas: '"title action" "description action"',
      gridTemplateColumns: 'auto max-content',
      columnGap: '15px',
      alignItems: 'center',
      minWidth: '300px',
      boxShadow: 'hsl(206 22% 7% / 35%) 0px 10px 38px -10px, hsl(206 22% 7% / 20%) 0px 10px 20px -15px',
    };

    // Enhanced colors for better contrast (WCAG AA compliance)
    const typeStyles = {
      success: { 
        borderColor: '#059669', 
        backgroundColor: '#ecfdf5',
        titleColor: '#065f46',
        descColor: '#047857'
      },
      error: { 
        borderColor: '#dc2626', 
        backgroundColor: '#fef2f2',
        titleColor: '#991b1b',
        descColor: '#b91c1c'
      },
      warning: { 
        borderColor: '#d97706', 
        backgroundColor: '#fffbeb',
        titleColor: '#92400e',
        descColor: '#b45309'
      },
      info: { 
        borderColor: '#2563eb', 
        backgroundColor: '#eff6ff',
        titleColor: '#1e40af',
        descColor: '#2563eb'
      },
    };

    return { 
      ...baseStyles, 
      borderColor: typeStyles[type as keyof typeof typeStyles].borderColor,
      backgroundColor: typeStyles[type as keyof typeof typeStyles].backgroundColor
    };
  };

  const getTypeColors = (type: string) => {
    const typeStyles = {
      success: { titleColor: '#065f46', descColor: '#047857' },
      error: { titleColor: '#991b1b', descColor: '#b91c1c' },
      warning: { titleColor: '#92400e', descColor: '#b45309' },
      info: { titleColor: '#1e40af', descColor: '#2563eb' },
    };
    return typeStyles[type as keyof typeof typeStyles];
  };

  return (
    <ToastContext.Provider value={{ showToast }}>
      <Toast.Provider swipeDirection="right">
        {children}
        {toasts.map((toast) => {
          const colors = getTypeColors(toast.type);
          return (
            <Toast.Root
              key={toast.id}
              style={getToastStyles(toast.type)}
              duration={5000}
              onOpenChange={(open) => {
                if (!open) removeToast(toast.id);
              }}
              // Enhanced a11y attributes
              role="alert"
              aria-live={toast.type === 'error' ? 'assertive' : 'polite'}
              aria-atomic="true"
            >
              <Toast.Title 
                style={{ 
                  gridArea: 'title', 
                  fontWeight: 600, 
                  color: colors.titleColor, 
                  fontSize: '15px',
                  margin: 0
                }}
              >
                {toast.type.charAt(0).toUpperCase() + toast.type.slice(1)}
              </Toast.Title>
              <Toast.Description 
                style={{ 
                  gridArea: 'description', 
                  margin: 0, 
                  color: colors.descColor, 
                  fontSize: '13px', 
                  lineHeight: 1.3 
                }}
              >
                {toast.message}
              </Toast.Description>
              <Toast.Action 
                style={{ gridArea: 'action' }} 
                altText={`Close ${toast.type} notification`}
              >
                <button
                  type="button"
                  aria-label={`Close ${toast.type} notification: ${toast.message}`}
                  title={`Close ${toast.type} notification`}
                  style={{
                    all: 'unset',
                    fontFamily: 'inherit',
                    borderRadius: '4px',
                    height: '25px',
                    width: '25px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#6b7280',
                    cursor: 'pointer',
                    border: '1px solid transparent',
                  }}
                  onClick={() => removeToast(toast.id)}
                  onFocus={(e) => {
                    e.target.style.outline = '2px solid #2563eb';
                    e.target.style.outlineOffset = '2px';
                  }}
                  onBlur={(e) => {
                    e.target.style.outline = 'none';
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'rgba(0, 0, 0, 0.05)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <Cross2Icon 
                    aria-hidden="true" 
                    style={{ width: '16px', height: '16px' }}
                  />
                </button>
              </Toast.Action>
            </Toast.Root>
          );
        })}
        <Toast.Viewport
          style={{
            position: 'fixed',
            bottom: 0,
            right: 0,
            display: 'flex',
            flexDirection: 'column',
            padding: '25px',
            gap: '10px',
            width: '390px',
            maxWidth: '100vw',
            margin: 0,
            listStyle: 'none',
            zIndex: 2147483647,
            outline: 'none',
          }}
          aria-label="Notifications"
        />
      </Toast.Provider>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextType => {
  const context = useContext(ToastContext);
  if (context === undefined) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};