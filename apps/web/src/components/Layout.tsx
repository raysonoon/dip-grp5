import { useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { Bot, RotateCcw, Send, Square, X } from "lucide-react";
import ChatMessageContent from "./ChatMessageContent";
import { useChatSession } from "../hooks/useChatSession";
import { Utensils } from "lucide-react";

const DISPLAY_FONT = "'Fraunces', serif";

// -------------------------------------------------------------
// 1. Floating Foodie Chatbot Component
// -------------------------------------------------------------
function FoodieChat() {
  const {
    input: chatInput,
    isGenerating: isTyping,
    messages: chatMessages,
    sendMessage,
    setInput: setChatInput,
    startNewSession: startNewChat,
    stopResponse,
  } = useChatSession();
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {chatOpen && (
        <div className="w-[360px] rounded-2xl border border-border bg-card shadow-2xl overflow-hidden">
          {/* Chat Header (Retains "Foodie" name) */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-card">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                <Bot className="w-4 h-4 text-primary-foreground" />
              </div>
              <div>
                <div className="text-sm font-semibold text-foreground">Foodie</div>
                <div className="text-xs text-[#4CAF50] flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#4CAF50] inline-block" />
                  Online
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={startNewChat}
                className="text-muted-foreground hover:text-foreground transition-colors p-1"
                aria-label="Start a new chat session"
                title="New chat"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setChatOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors p-1"
                aria-label="Close chat"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Chat Messages */}
          <div className="p-4 h-72 overflow-y-auto flex flex-col gap-3 bg-background">
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[82%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground rounded-br-sm"
                      : "bg-card border border-border text-foreground rounded-bl-sm"
                  }`}
                >
                  {msg.role === "bot" ? (
                    <ChatMessageContent answer={msg.text} sources={msg.sources} />
                  ) : (
                    msg.text
                  )}
                </div>
              </div>
            ))}
            {isTyping && (
              <div className="flex justify-start">
                <div className="px-4 py-3 rounded-2xl bg-card border border-border rounded-bl-sm">
                  <div className="flex gap-1 items-center">
                    {[0, 1, 2].map((i) => (
                      <div
                        key={i}
                        className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Chat Input */}
          <div className="px-4 py-4 border-t border-border bg-card">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendMessage(chatInput)}
                placeholder="Ask anything about campus food..."
                className="flex-1 bg-background border border-border rounded-xl px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40 transition-colors"
              />
              {isTyping ? (
                <button
                  type="button"
                  onClick={stopResponse}
                  aria-label="Stop generating response"
                  title="Stop"
                  className="w-10 h-10 rounded-xl bg-destructive text-destructive-foreground flex items-center justify-center hover:opacity-90 transition-opacity flex-shrink-0"
                >
                  <Square className="w-4 h-4 fill-current" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => sendMessage(chatInput)}
                  disabled={!chatInput.trim()}
                  aria-label="Send message"
                  className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center hover:opacity-90 disabled:opacity-50 transition-opacity flex-shrink-0"
                >
                  <Send className="w-4 h-4 text-primary-foreground" />
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Chat Toggle Button */}
      <button
        type="button"
        onClick={() => setChatOpen((o) => !o)}
        className="flex items-center gap-2.5 px-5 py-3.5 rounded-full bg-primary text-primary-foreground font-semibold text-sm shadow-lg hover:opacity-90 transition-opacity"
        aria-label="Open Foodie chatbot"
      >
        {chatOpen ? <X className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
        {!chatOpen && "Ask Foodie"}
      </button>
    </div>
  );
}

// -------------------------------------------------------------
// 2. Shared Layout Component
// -------------------------------------------------------------
export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground font-sans">
      {/* Sticky Header Nav (position: sticky; top: 0) with "NTUmmy" brand name */}
      <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex h-16 items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-xl font-bold tracking-tight text-foreground">
           <div className="flex items-center gap-2.5">

            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">

              <Utensils className="w-4 h-4 text-primary-foreground" />

            </div>

            <span

              className="text-lg font-bold text-foreground"

              style={{ fontFamily: DISPLAY_FONT }}>
             NTUmmy</span>
           </div>
          </Link>
          <nav className="flex items-center gap-6 text-sm font-medium">
          </nav>
        </div>
      </header>

      {/* Renders current active page view */}
      <main className="flex-1">
        <Outlet />
      </main>

      {/* ── FOOTER ───────────────────────────────────── */}
      <footer className="border-t border-border py-10">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-primary flex items-center justify-center">
              <Utensils className="w-3 h-3 text-primary-foreground" />
            </div>
            <span
              className="text-sm font-bold"
              style={{ fontFamily: DISPLAY_FONT }}
            >
              NTUmmy
            </span>
          </div>
          <p className="text-xs text-muted-foreground">Made by NTU students, for NTU students.</p>
          <div className="flex gap-6 text-xs text-muted-foreground">
            {["About", "Contribute", "Privacy"].map((l) => (
              <a
                key={l}
                href="#"
                className="hover:text-foreground transition-colors"
              >
                {l}
              </a>
            ))}
          </div>
        </div>
      </footer>

      {/* Shared Floating Chatbot Widget */}
      <FoodieChat />
    </div>
  );
}
