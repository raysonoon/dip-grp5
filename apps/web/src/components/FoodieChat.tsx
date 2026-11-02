import { useEffect, useRef, useState } from "react";
import { RotateCcw, RotateCw, Send, Square, X } from "lucide-react";
import { MAX_CHAT_QUESTION_LENGTH } from "../api/chat";
import { useChat } from "../contexts/ChatContext";
import { useChatSession } from "../hooks/useChatSession";
import ChatMessageContent from "./ChatMessageContent";
import FoodieAvatar from "./FoodieAvatar";
import VendorWheel from "./VendorWheel";
import "./foodieChat.css";

const MASCOT_GREETINGS = ["Hey hey! 👋", "Ready to makan? 🍜", "You found me! ✨"];

export default function FoodieChat() {
  const { input, isGenerating, messages, sendMessage, setInput, startNewSession, stopResponse, wheelVendors, removeWheelVendor } = useChatSession();
  const { chatOpen: open, closeChat, toggleChat } = useChat();
  const [wheelOpen, setWheelOpen] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const [greetingCount, setGreetingCount] = useState(0);
  const [showGreeting, setShowGreeting] = useState(false);
  const greetingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (greetingTimer.current) clearTimeout(greetingTimer.current);
  }, []);

  function greet() {
    if (greetingTimer.current) clearTimeout(greetingTimer.current);
    setGreetingCount((count) => count + 1);
    setShowGreeting(true);
    greetingTimer.current = setTimeout(() => setShowGreeting(false), 2200);
  }

  useEffect(() => {
    const container = messagesRef.current;
    if (container) container.scrollTop = messages.length === 1 ? 0 : container.scrollHeight;
  }, [messages, open, isGenerating]);

  return (
    <div className="foodie-widget">
      {open && <section className="foodie-window" data-chat-window aria-label="Chat with Foodie">
        <header className="foodie-header">
          <div className="foodie-avatar-interaction">
            <button type="button" className="foodie-avatar-button" onClick={greet} aria-label="Say hi to Foodie"><FoodieAvatar key={greetingCount} speaking={isGenerating} waving={showGreeting} /></button>
            {showGreeting && <span className="foodie-avatar-greeting" role="status">{MASCOT_GREETINGS[(greetingCount - 1) % MASCOT_GREETINGS.length]}</span>}
          </div>
          <div className="foodie-heading"><strong>Foodie<span>✦</span></strong><span>Your campus makan buddy</span></div>
          <div className="foodie-header-actions">
            <button type="button" onClick={() => { setWheelOpen(false); startNewSession(); }} aria-label="Start a new chat session" title="New chat"><RotateCcw size={16} /></button>
            <button type="button" onClick={closeChat} aria-label="Close chat"><X size={18} /></button>
          </div>
        </header>

        <div id="foodie-chat-panel">
          <div className="foodie-messages" ref={messagesRef} role="log" aria-label="Chat messages" aria-live="polite">
            {messages.length === 1 && <button type="button" className="foodie-welcome-art" onClick={greet} aria-label="Give Foodie a wave"><FoodieAvatar large key={greetingCount} /><span className="foodie-welcome-star" aria-hidden="true">✦</span><span key={`wave-${greetingCount}`} className="foodie-welcome-wave" aria-hidden="true">👋</span></button>}
            {messages.map((message, index) => <div key={index} className={`foodie-message ${message.role === "user" ? "foodie-message-user" : "foodie-message-bot"}`}>
              {message.role === "bot" ? <ChatMessageContent answer={message.text} sources={message.sources} /> : message.text}
            </div>)}
            {isGenerating && <div className="foodie-thinking" role="status" aria-label="Foodie is thinking"><span /><span /><span /><small>Foodie is thinking…</small></div>}
          </div>

          {wheelVendors.length >= 2 && <button type="button" className="vendor-wheel-invite" disabled={isGenerating} onClick={() => setWheelOpen(true)}><RotateCw size={15} aria-hidden="true" /> Spin the wheel <span>{wheelVendors.length} places</span></button>}

          <form className="foodie-composer" onSubmit={(event) => { event.preventDefault(); void sendMessage(input); }}>
            <div className="foodie-input-row">
              <input value={input} onChange={(event) => setInput(event.target.value)} maxLength={MAX_CHAT_QUESTION_LENGTH} aria-describedby="foodie-chat-character-count" aria-label="Message Foodie" placeholder="What are you craving today?" />
              {isGenerating ? <button type="button" onClick={stopResponse} aria-label="Stop generating response" className="foodie-send foodie-stop"><Square size={15} fill="currentColor" /></button>
                : <button type="submit" disabled={!input.trim()} aria-label="Send message" className="foodie-send"><Send size={17} /></button>}
            </div>
            <span id="foodie-chat-character-count" className="foodie-character-count">{input.length}/{MAX_CHAT_QUESTION_LENGTH}</span>
          </form>
        </div>
        <div className="foodie-footer-note">A little help with your next happy meal.</div>
      </section>}

      {wheelOpen && <VendorWheel vendors={wheelVendors} onRemove={removeWheelVendor} onClose={() => setWheelOpen(false)} />}

      <button type="button" className={`foodie-launcher ${open ? "foodie-launcher-open" : ""}`} onClick={toggleChat} aria-label={open ? "Close Foodie chatbot" : "Open Foodie chatbot"} aria-expanded={open}>
        {open ? <X size={20} /> : <><FoodieAvatar /><span><strong>Time to eat?</strong><small>Ask Foodie</small></span><span className="foodie-launcher-sparkle">✦</span></>}
      </button>
    </div>
  );
}
