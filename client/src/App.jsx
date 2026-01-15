import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'
import { useState, useEffect, useRef } from 'react'
import Prism from './components/Prism'
import Stars from './components/Stars'
import Sidebar from './components/Sidebar'
import SendButton from './components/SendButton'
import MenuButton from './components/MenuButton'
import './App.css'
import { SignedIn, SignedOut, SignInButton, UserButton, useUser } from "@clerk/clerk-react";

// Use relative URL in production, localhost in development
const API_URL = import.meta.env.PROD ? '' : 'http://127.0.0.1:8000';

function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [checkpointId, setCheckpointId] = useState(null)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [currentChatId, setCurrentChatId] = useState(null)
  const [isMobile, setIsMobile] = useState(false)
  const messagesEndRef = useRef(null)
  const landingTextareaRef = useRef(null)
  const chatTextareaRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  const { user } = useUser();

  // Detect mobile device
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };

    checkMobile();
    window.addEventListener('resize', checkMobile);

    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {

    scrollToBottom()
  }, [messages])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage = input
    setInput("")
    // Add user message
    setMessages(prev => [...prev, { type: 'user', content: userMessage }])
    setIsLoading(true)

    // Add placeholder for AI response with initial thinking state
    setMessages(prev => [...prev, {
      type: 'ai',
      content: '',
      sources: [],
      steps: {
        searching: { status: 'idle', query: '' },
        reading: { status: 'idle', urls: [] },
        writing: { status: 'idle' }
      }
    }])

    try {
      const encodedMessage = encodeURIComponent(userMessage);
      const url = `${API_URL}/chat_stream/${encodedMessage}${checkpointId ? `?checkpoint_id=${checkpointId}` : ''}`;

      const eventSource = new EventSource(url);
      let currentContent = "";

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'checkpoint') {
            setCheckpointId(data.checkpoint_id);
          } else if (data.type === 'search_start') {
            setMessages(prev => {
              const newMessages = [...prev];
              const lastMessage = newMessages[newMessages.length - 1];
              if (lastMessage.type === 'ai') {
                lastMessage.steps.searching = { status: 'active', query: data.query };
              }
              return newMessages;
            });
          } else if (data.type === 'search_results') {
            setMessages(prev => {
              const newMessages = [...prev];
              const lastMessage = newMessages[newMessages.length - 1];
              if (lastMessage.type === 'ai') {
                lastMessage.steps.searching.status = 'completed';
                lastMessage.steps.reading = { status: 'active', urls: data.urls };
                lastMessage.sources = data.urls;
              }
              return newMessages;
            });
          } else if (data.type === 'content') {
            currentContent += data.content;
            setMessages(prev => {
              const newMessages = [...prev];
              const lastMessage = newMessages[newMessages.length - 1];
              if (lastMessage.type === 'ai') {
                if (lastMessage.steps.reading.status === 'active') {
                  lastMessage.steps.reading.status = 'completed';
                }
                if (lastMessage.steps.searching.status === 'active') {
                  lastMessage.steps.searching.status = 'completed';
                }
                lastMessage.steps.writing.status = 'active';
                lastMessage.content = currentContent;
              }
              return newMessages;
            });
          } else if (data.type === 'end') {
            setMessages(prev => {
              const newMessages = [...prev];
              const lastMessage = newMessages[newMessages.length - 1];
              if (lastMessage.type === 'ai') {
                lastMessage.steps.writing.status = 'completed';
              }
              return newMessages;
            });
            eventSource.close();
            setIsLoading(false);
          }
        } catch (err) {
          console.error("Error parsing SSE data:", err);
        }
      };

      eventSource.onerror = (error) => {
        // console.error("EventSource failed:", error); // Close silently on end usually
        eventSource.close();
        setIsLoading(false);
      };

    } catch (error) {
      console.error("Error:", error);
      setIsLoading(false);
    }
  }

  const handleNewChat = () => {
    setMessages([]);
    setCheckpointId(null);
    setCurrentChatId(null);
    setInput("");
  };

  const handleSelectChat = async (chatId) => {
    try {
      const url = user ? `${API_URL}/chats/${chatId}?user_id=${user.id}` : `${API_URL}/chats/${chatId}`;
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        setMessages(data.messages || []);
        setCheckpointId(data.checkpoint_id);
        setCurrentChatId(chatId);
      }
    } catch (error) {
      console.error('Error loading chat:', error);
    }
  };

  const saveChat = async (msgs, cpId, chatId) => {
    try {
      // Only save if user is signed in
      if (!user) return;

      // Generate title from first user message
      const firstUserMsg = msgs.find(m => m.type === 'user');
      const title = firstUserMsg ? firstUserMsg.content.substring(0, 50) : 'New Chat';

      const chatData = {
        user_id: user.id,  // Add user_id from Clerk
        title,
        messages: msgs,
        checkpoint_id: cpId
      };

      if (chatId) {
        // Update existing chat
        const url = `${API_URL}/chats/${chatId}?user_id=${user.id}`;
        await fetch(url, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(chatData)
        });
      } else {
        // Create new chat
        const response = await fetch(`${API_URL}/chats`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(chatData)
        });
        if (response.ok) {
          const data = await response.json();
          setCurrentChatId(data.id);
        }
      }
    } catch (error) {
      console.error('Error saving chat:', error);
    }
  };

  // Auto-save chat when messages change
  useEffect(() => {
    if (messages.length > 0 && !isLoading) {
      saveChat(messages, checkpointId, currentChatId);
    }
  }, [messages, isLoading]);

  // Helper Components
  const MenuIcon = () => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 6H20M4 12H20M4 18H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );

  const PlusIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="12" y1="5" x2="12" y2="19"></line>
      <line x1="5" y1="12" x2="19" y2="12"></line>
    </svg>
  );

  const MicIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
      <line x1="12" y1="19" x2="12" y2="23"></line>
      <line x1="8" y1="23" x2="16" y2="23"></line>
    </svg>
  );

  const ThinkingProcess = ({ steps }) => {
    if (!steps) return null;
    const hasActivity = steps.searching.status !== 'idle' || steps.writing.status !== 'idle';
    if (!hasActivity) return null;

    return (
      <div className="process-timeline">
        {steps.searching.status !== 'idle' && (
          <div className={`step ${steps.searching.status}`}>
            <div className="step-indicator"></div>
            <div className="step-title">Searching the web</div>
            <div className="step-content">
              <div className="search-query-bubble">
                <span style={{ marginRight: '5px' }}>🔍</span>
                {steps.searching.query}
              </div>
            </div>
          </div>
        )}
        {steps.reading.status !== 'idle' && (
          <div className={`step ${steps.reading.status}`}>
            <div className="step-indicator"></div>
            <div className="step-title">Reading sources</div>
            <div className="step-content">
              <div className="sources-grid">
                {steps.reading.urls.map((url, i) => {
                  try {
                    const hostname = new URL(url).hostname.replace('www.', '');
                    return (
                      <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="source-card">
                        {hostname}
                      </a>
                    )
                  } catch (e) { return null; }
                })}
              </div>
            </div>
          </div>
        )}
        {steps.writing.status !== 'idle' && (
          <div className={`step ${steps.writing.status}`}>
            <div className="step-indicator"></div>
            <div className="step-title">Writing answer</div>
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      <div className="background-wrapper">
        {isMobile ? <Stars count={150} /> : <Prism />}

      </div>

      <Sidebar
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
        currentChatId={currentChatId}
      />

      <div className="app-container">
        <header className="header">
          <div className="logo-section">
            <MenuButton onClick={() => setIsSidebarOpen(true)} />
            <h1 className="logo-text">QIRO.AI</h1>
          </div>
          <div className="auth-section">
            <header>
              <SignedOut>
                <SignInButton mode="modal">
                  <button className="sign-in-btn">Sign In</button>
                </SignInButton>
              </SignedOut>
              <SignedIn>
                <UserButton showingName={false} />
              </SignedIn>
            </header>
          </div>
        </header>

        {messages.length === 0 ? (
          <div className="landing-container">
            <div className="landing-content">
              <h1 className="greeting-text">
                HI {user?.firstName ? user.firstName.toUpperCase() : 'USER'}
              </h1>

              <div className="landing-input-wrapper" onClick={() => landingTextareaRef.current?.focus()}>
                <h3>Ask Qiro AI</h3>
                <form onSubmit={handleSubmit} className="landing-input-form">

                  <textarea
                    ref={landingTextareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder=""
                    className="landing-textarea"
                    rows={1}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSubmit(e);
                      }
                    }}
                  />

                  <div className="landing-input-actions">
                    <SendButton type="submit" disabled={isLoading || !input.trim()} />
                  </div>
                </form>
              </div>

              <div className="suggestion-chips">
                <button className="chip">
                  <span>✎</span> Write anything
                </button>
                <button className="chip">
                  <span>💡</span> Help me learn
                </button>
                <button className="chip">
                  <span>⚡</span> Boost my productivity
                </button>
                <button className="chip">
                  <span>☺</span> Tell a joke
                </button>
              </div>

            </div>
          </div>
        ) : (
          <>
            <div className="chat-container">
              {messages.map((msg, index) => (
                <div key={index} className={`message ${msg.type}`}>

                  {msg.type === 'ai' && msg.steps && <ThinkingProcess steps={msg.steps} />}

                  {msg.content && (
                    <div className="message-content">
                      <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              ))}
              {/* Helper when waiting but no timeline events yet */}
              {isLoading && messages.length > 0 && messages[messages.length - 1].steps.searching.status === 'idle' && messages[messages.length - 1].steps.writing.status === 'idle' && (
                <div className="loading-indicator">Thinking...</div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <div className="input-area">
              <form onSubmit={handleSubmit} className="input-form" onClick={() => chatTextareaRef.current?.focus()}>
                <button type="button" className="icon-btn">
                  <PlusIcon />
                </button>

                <textarea
                  ref={chatTextareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask Qiro AI"
                  rows={1}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSubmit(e);
                    }
                  }}
                  style={{ height: 'auto', minHeight: '24px' }}
                  onInput={(e) => {
                    e.target.style.height = 'auto';
                    e.target.style.height = e.target.scrollHeight + 'px';
                  }}
                />

                <div className="input-actions">
                  <SendButton type="submit" disabled={isLoading || !input.trim()} />
                </div>

              </form>
            </div>
          </>
        )}
      </div>
    </>
  )
}

export default App
