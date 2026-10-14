import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Bot, RotateCcw, Send, Square, X } from "lucide-react";
import ChatMessageContent from "./ChatMessageContent";
import { useChatSession } from "../hooks/useChatSession";
import Footer from "./Footer";
import Header from "./Header";

// -------------------------------------------------------------
// 1. Floating Foodie Chatbot Component
// -------------------------------------------------------------
export function FoodieChat() {
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
    <div className="fixed bottom-4 right-4 sm:bottom-6 sm:right-6 z-50 flex flex-col items-end gap-3">
      {chatOpen && (
        <div data-chat-window className="w-[calc(100vw-2rem)] sm:w-[360px] rounded-2xl border border-border bg-card shadow-2xl overflow-hidden">
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
        className="flex items-center gap-2.5 px-5 py-3.5 rounded-full bg-primary text-primary-foreground font-semibold text-sm shadow-lg cursor-pointer hover:opacity-90 transition-opacity"
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
    <div className="min-h-screen supports-[height:100dvh]:min-h-dvh flex flex-col bg-background text-foreground font-sans">
      {/* Sticky Header Nav */}
      <Header />

      {/* Renders current active page view */}
      <main className="flex-1">
        <Outlet />
      </main>

      {/* ── FOOTER ───────────────────────────────────── */}
      <Footer />

      {/* Shared Floating Chatbot Widget */}
      <FoodieChat />
    </div>
  );
}
