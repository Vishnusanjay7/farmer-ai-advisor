"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { getCurrentUser, getAuthToken, signOutUser, UserProfile } from "@/lib/supabase";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

const isValidUUID = (id: string | null | undefined): boolean => {
  return typeof id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id.trim());
};

const SUPPORTED_LANGUAGES = [
  { code: "hi-IN", label: "हिंदी (Hindi)", greeting: "नमस्ते किसान भाई! मैं आपकी क्या सहायता कर सकता हूँ?" },
  { code: "te-IN", label: "తెలుగు (Telugu)", greeting: "నమస్కారం రైతు సోదరా! నేను మీకు ఎలా సహాయపడగలను?" },
  { code: "ta-IN", label: "தமிழ் (Tamil)", greeting: "வணக்கம் விவசாய நண்பரே! நான் உங்களுக்கு எவ்வாறு உதவ முடியும்?" },
  { code: "mr-IN", label: "मराठी (Marathi)", greeting: "नमस्कार शेतकरी मित्रा! मी तुम्हाला कशी मदत करू शकतो?" },
  { code: "kn-IN", label: "ಕನ್ನಡ (Kannada)", greeting: "ನಮಸ್ಕಾರ ರೈತ ಮಿತ್ರರೇ! ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?" },
  { code: "bn-IN", label: "বাংলা (Bengali)", greeting: "নমস্কার কৃষক বন্ধু! আমি আপনাকে কীভাবে সাহায্য করতে পারি?" },
  { code: "gu-IN", label: "ગુજરાતી (Gujarati)", greeting: "નમસ્તે ખેડૂત મિત્ર! હું તમને કેવી રીતે મદદ કરી શકું?" },
  { code: "ml-IN", label: "മലയാളം (Malayalam)", greeting: "നമസ്കാരം കർഷക സുഹൃത്തേ! ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കണം?" },
  { code: "pa-IN", label: "ਪੰਜਾਬੀ (Punjabi)", greeting: "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ ਕਿਸਾਨ ਵੀਰੋ! ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?" },
  { code: "od-IN", label: "ଓଡ଼ିଆ (Odia)", greeting: "ନମସ୍କାର ଚାଷୀ ଭାଇ! ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?" },
  { code: "en-IN", label: "English", greeting: "Welcome Farmer! How can I assist you with your farming today?" },
];

interface AdvisorCitation {
  title: string;
  issuing_authority: string;
  official_url?: string;
  relevance_score: number;
  data_origin?: string;
  arrival_date?: string;
}

interface ConversationMessage {
  id: string;
  role: "user" | "advisor";
  text: string;
  language: string;
  intent?: string;
  inputChannel?: "voice" | "text";
  extractedContext?: Record<string, any>;
  inheritedContext?: Record<string, any>;
  citations?: AdvisorCitation[];
  dataOrigin?: string;
  isGrounded?: boolean;
  abstained?: boolean;
  abstentionReason?: string;
  llmCalled?: boolean;
  audioBase64?: string;
  createdAt: string;
}

interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  total_turns: number;
  last_query?: string;
  detected_language?: string;
}

export default function FarmerAdvisorPage() {
  const [selectedLanguage, setSelectedLanguage] = useState("hi-IN");
  const [user, setUser] = useState<UserProfile | null>(null);
  const [conversationId, setConversationId] = useState<string>("");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [textInput, setTextInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [audioPlayingId, setAudioPlayingId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Audio refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const chatBottomRef = useRef<HTMLDivElement | null>(null);

  // Load user profile & token on mount
  useEffect(() => {
    async function loadAuth() {
      const u = await getCurrentUser();
      setUser(u);
    }
    loadAuth();
  }, []);

  // Initialize conversationId
  useEffect(() => {
    const storedConv = sessionStorage.getItem("farmer_conv_id");
    if (storedConv && isValidUUID(storedConv)) {
      setConversationId(storedConv);
    } else {
      const freshId = crypto.randomUUID();
      sessionStorage.setItem("farmer_conv_id", freshId);
      setConversationId(freshId);
    }
  }, []);

  // Load conversations list for logged-in user
  useEffect(() => {
    async function fetchUserConversations() {
      if (!user) return;
      try {
        const token = await getAuthToken();
        const res = await fetch(`${BACKEND_URL}/api/v1/conversations`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const data = await res.json();
          setConversations(data.conversations || []);
        }
      } catch (err) {
        console.error("Failed to load user conversations:", err);
      }
    }
    fetchUserConversations();
  }, [user, conversationId]);

  // Scroll to bottom on new messages
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Load specific conversation turns
  const loadConversation = async (convId: string) => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const token = await getAuthToken();
      const res = await fetch(`${BACKEND_URL}/api/v1/conversations/${convId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!res.ok) {
        if (res.status === 403) {
          setErrorMessage("You do not have permission to view this conversation.");
        } else {
          setErrorMessage("Could not load conversation history.");
        }
        setIsLoading(false);
        return;
      }

      const data = await res.json();
      setConversationId(data.conversation_id);
      sessionStorage.setItem("farmer_conv_id", data.conversation_id);

      const loadedMessages: ConversationMessage[] = [];
      for (const turn of data.turns) {
        // User turn
        loadedMessages.push({
          id: `u-${turn.query_id}`,
          role: "user",
          text: turn.query_text,
          language: turn.detected_language,
          inputChannel: turn.input_channel,
          createdAt: turn.created_at,
        });
        // Advisor turn
        loadedMessages.push({
          id: `a-${turn.query_id}`,
          role: "advisor",
          text: turn.response_text,
          language: turn.detected_language,
          intent: turn.classified_intent,
          extractedContext: turn.extracted_entities,
          citations: turn.citations,
          isGrounded: turn.is_grounded,
          abstained: turn.disclaimer_applied,
          createdAt: turn.created_at,
        });
      }
      setMessages(loadedMessages);
      setIsSidebarOpen(false);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load conversation.");
    } finally {
      setIsLoading(false);
    }
  };

  // Start fresh conversation
  const handleNewChat = () => {
    const freshId = crypto.randomUUID();
    sessionStorage.setItem("farmer_conv_id", freshId);
    setConversationId(freshId);
    setMessages([]);
    setTextInput("");
    setErrorMessage(null);
    setIsSidebarOpen(false);
  };

  // Delete conversation
  const handleDeleteConversation = async (e: React.MouseEvent, convId: string) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this conversation?")) return;
    try {
      const token = await getAuthToken();
      const res = await fetch(`${BACKEND_URL}/api/v1/conversations/${convId}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        setConversations((prev) => prev.filter((c) => c.id !== convId));
        if (conversationId === convId) {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Delete conversation failed:", err);
    }
  };

  // Submit text or voice query
  const submitQuery = async (queryText: string, channel: "text" | "voice" = "text") => {
    if (!queryText.trim() || isLoading) return;

    setErrorMessage(null);
    setIsLoading(true);

    const userMessage: ConversationMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text: queryText,
      language: selectedLanguage,
      inputChannel: channel,
      createdAt: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setTextInput("");

    try {
      const token = await getAuthToken();
      const res = await fetch(`${BACKEND_URL}/api/v1/advisor/query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          query: queryText,
          language: selectedLanguage,
          input_channel: channel,
          conversation_id: isValidUUID(conversationId) ? conversationId : undefined,
        }),
      });

      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }

      const data = await res.json();

      // Ensure conversationId matches backend response
      if (data.conversation_id && isValidUUID(data.conversation_id)) {
        setConversationId(data.conversation_id);
        sessionStorage.setItem("farmer_conv_id", data.conversation_id);
      }

      // Request regional TTS audio for the final response
      let audioBase64: string | undefined = undefined;
      try {
        const ttsRes = await fetch(`${BACKEND_URL}/api/v1/voice/tts`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: data.response_text.slice(0, 450), // clean synthesis
            language: data.language || selectedLanguage,
          }),
        });
        if (ttsRes.ok) {
          const ttsData = await ttsRes.json();
          audioBase64 = ttsData.audio_base64;
        }
      } catch (ttsErr) {
        console.warn("TTS fetch fallback:", ttsErr);
      }

      const advisorMessage: ConversationMessage = {
        id: data.query_id || crypto.randomUUID(),
        role: "advisor",
        text: data.response_text,
        language: data.language,
        intent: data.intent,
        inputChannel: data.input_channel,
        extractedContext: data.extracted_context,
        inheritedContext: data.inherited_context,
        citations: data.citations,
        dataOrigin: data.data_origin,
        isGrounded: data.is_grounded,
        abstained: data.abstained,
        abstentionReason: data.abstention_reason,
        llmCalled: data.llm_called,
        audioBase64: audioBase64,
        createdAt: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, advisorMessage]);

      // Auto-play TTS if from voice query
      if (channel === "voice" && audioBase64) {
        playAudio(advisorMessage.id, audioBase64);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to receive response from advisor. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  // Audio Playback
  const playAudio = (msgId: string, base64: string) => {
    if (activeAudioRef.current) {
      activeAudioRef.current.pause();
    }
    const audio = new Audio(`data:audio/wav;base64,${base64}`);
    activeAudioRef.current = audio;
    setAudioPlayingId(msgId);

    audio.onended = () => {
      setAudioPlayingId(null);
    };
    audio.onerror = () => {
      setAudioPlayingId(null);
    };
    audio.play().catch((e) => console.warn("Audio autoplay prevented:", e));
  };

  const stopAudio = () => {
    if (activeAudioRef.current) {
      activeAudioRef.current.pause();
    }
    setAudioPlayingId(null);
  };

  // Voice Recording Control
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        stream.getTracks().forEach((track) => track.stop());
        await processVoiceUpload(audioBlob);
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingSeconds(0);
      timerIntervalRef.current = setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      alert("Microphone access is required for voice query. Please enable mic permissions.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
    }
  };

  const processVoiceUpload = async (audioBlob: Blob) => {
    setIsLoading(true);
    try {
      const formData = new FormData();
      formData.append("audio_file", audioBlob, "recording.wav");
      formData.append("language", selectedLanguage);

      const res = await fetch(`${BACKEND_URL}/api/v1/voice/stt`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Speech transcription failed.");
      }

      const data = await res.json();
      if (data.transcript) {
        await submitQuery(data.transcript, "voice");
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to transcribe audio.");
      setIsLoading(false);
    }
  };

  const handleSignOut = async () => {
    await signOutUser();
    setUser(null);
    setConversations([]);
    handleNewChat();
  };

  const currentLangConfig = SUPPORTED_LANGUAGES.find((l) => l.code === selectedLanguage) || SUPPORTED_LANGUAGES[0];

  return (
    <div className="app-shell">
      {/* Mobile Drawer Backdrop */}
      <div
        className={`drawer-backdrop ${isSidebarOpen ? "open" : ""}`}
        onClick={() => setIsSidebarOpen(false)}
      />

      {/* Sidebar: Conversation History & User Profile */}
      <aside className={`app-sidebar ${isSidebarOpen ? "open" : ""}`}>
        <div className="sidebar-header">
          <button className="btn-new-chat" onClick={handleNewChat}>
            <span>+</span>
            <span>New Advisory Chat</span>
          </button>
        </div>

        <div className="sidebar-history-container">
          {conversations.length === 0 ? (
            <div style={{ padding: "20px 14px", color: "var(--text-muted)", fontSize: "13px", textAlign: "center" }}>
              {user ? "No past chats yet. Ask a question to start!" : "Sign in to save and access your past conversations."}
            </div>
          ) : (
            <div className="history-group">
              <div className="history-group-title">Recent Conversations</div>
              {conversations.map((c) => (
                <button
                  key={c.id}
                  className={`history-item ${conversationId === c.id ? "active" : ""}`}
                  onClick={() => loadConversation(c.id)}
                >
                  <span className="history-item-content">
                    {c.title.replace("Advisory Query: ", "")}
                  </span>
                  <span
                    className="btn-delete-conv"
                    title="Delete chat"
                    onClick={(e) => handleDeleteConversation(e, c.id)}
                  >
                    🗑️
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Sidebar Footer with Auth Status */}
        <div className="sidebar-footer">
          {user ? (
            <div className="user-profile-bar">
              <div className="user-avatar">{user.fullName?.charAt(0).toUpperCase() || "F"}</div>
              <div className="user-info">
                <div className="user-name">{user.fullName || user.email}</div>
                <div className="user-auth-badge">Verified Farmer</div>
              </div>
              <button className="btn-auth-action" onClick={handleSignOut} title="Sign Out">
                Exit
              </button>
            </div>
          ) : (
            <div className="user-profile-bar">
              <div className="user-avatar">👤</div>
              <div className="user-info">
                <div className="user-name">Guest Farmer</div>
                <div className="user-auth-badge">Session Only</div>
              </div>
              <Link href="/login" className="btn-auth-action">
                Sign In
              </Link>
            </div>
          )}
        </div>
      </aside>

      {/* Main Content View */}
      <main className="main-content">
        {/* Top Header Bar */}
        <header className="top-header">
          <div className="header-left">
            <button
              className="btn-menu-toggle"
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              aria-label="Toggle history menu"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="12" x2="21" y2="12"></line>
                <line x1="3" y1="6" x2="21" y2="6"></line>
                <line x1="3" y1="18" x2="21" y2="18"></line>
              </svg>
            </button>

            <div className="brand-section">
              <div className="brand-badge">🌾</div>
              <div className="brand-text">
                <h1>Krishi Vaani</h1>
                <p>Regional Voice AI Advisory for Farmers</p>
              </div>
            </div>
          </div>

          <div className="header-right">
            {/* Native Script 11-Language Selector */}
            <select
              className="lang-selector-select"
              value={selectedLanguage}
              onChange={(e) => setSelectedLanguage(e.target.value)}
              aria-label="Select Regional Language"
            >
              {SUPPORTED_LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </select>
          </div>
        </header>

        {/* Message Stream */}
        <div className="chat-container">
          {messages.length === 0 ? (
            /* Empty State with 4 Quick Prompt Chips */
            <div className="empty-state-card">
              <div className="empty-state-badge">🌱</div>
              <h2 className="empty-state-greeting">{currentLangConfig.greeting}</h2>
              <p className="empty-state-subtext">
                Ask in your native language by speaking or typing. Receive verified prices from Agmarknet, pest advice from ICAR, and central schemes.
              </p>

              <div className="prompt-chips-grid">
                <button
                  className="prompt-chip"
                  onClick={() => submitQuery("What is the wheat price in Indore mandi?", "text")}
                >
                  <span className="prompt-chip-icon">📊</span>
                  <span className="prompt-chip-title">Mandi Price</span>
                  <span className="prompt-chip-query">What is the wheat price in Indore?</span>
                </button>

                <button
                  className="prompt-chip"
                  onClick={() => submitQuery("How to control yellow stem borer in paddy?", "text")}
                >
                  <span className="prompt-chip-icon">🐛</span>
                  <span className="prompt-chip-title">Pest Management</span>
                  <span className="prompt-chip-query">How to control yellow stem borer in paddy?</span>
                </button>

                <button
                  className="prompt-chip"
                  onClick={() => submitQuery("Which fertilizer dosage should I apply for wheat?", "text")}
                >
                  <span className="prompt-chip-icon">🧪</span>
                  <span className="prompt-chip-title">Fertilizer & Nutrition</span>
                  <span className="prompt-chip-query">What fertilizer dosage for wheat?</span>
                </button>

                <button
                  className="prompt-chip"
                  onClick={() => submitQuery("Am I eligible for PM-KISAN yojana benefits?", "text")}
                >
                  <span className="prompt-chip-icon">📜</span>
                  <span className="prompt-chip-title">Government Schemes</span>
                  <span className="prompt-chip-query">PM-KISAN yojana eligibility criteria</span>
                </button>
              </div>
            </div>
          ) : (
            /* Active Message History */
            messages.map((msg) => (
              <div key={msg.id} className={`message-row ${msg.role}`}>
                {msg.role === "user" ? (
                  <div className="user-bubble">{msg.text}</div>
                ) : (
                  <div className="advisor-card">
                    {/* Metadata Header */}
                    <div className="advisor-card-meta">
                      {msg.intent && <span className="badge-intent">{msg.intent.replace(/_/g, " ")}</span>}
                      {msg.dataOrigin && (
                        <span className={msg.dataOrigin === "production_live" ? "badge-origin-live" : "badge-origin-cached"}>
                          {msg.dataOrigin === "production_live" ? "● Live Verified Source" : "● Cached Data"}
                        </span>
                      )}
                    </div>

                    {/* Grounded Text Response */}
                    <div className="advisor-text-content">{msg.text}</div>

                    {/* Audio Player Component */}
                    {msg.audioBase64 && (
                      <div className="audio-player-bar">
                        <button
                          className="btn-play-audio"
                          onClick={() => {
                            if (audioPlayingId === msg.id) {
                              stopAudio();
                            } else {
                              playAudio(msg.id, msg.audioBase64!);
                            }
                          }}
                          aria-label="Play regional speech"
                        >
                          {audioPlayingId === msg.id ? "⏸" : "▶"}
                        </button>
                        <span className="audio-track-label">
                          {audioPlayingId === msg.id ? "Speaking in regional language..." : "Listen to audio response"}
                        </span>
                      </div>
                    )}

                    {/* Citations List */}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="citations-box">
                        <div className="citations-header">Verified Sources & Documents:</div>
                        <div>
                          {msg.citations.map((c, i) => (
                            <a
                              key={i}
                              href={c.official_url || "#"}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="citation-chip"
                            >
                              <span>🏛️</span>
                              <span>{c.issuing_authority}</span>
                            </a>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}

          {/* Loading Indicator */}
          {isLoading && (
            <div className="message-row advisor">
              <div className="advisor-card" style={{ opacity: 0.85 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "14px", color: "var(--text-secondary)" }}>
                  <span style={{ animation: "spin 1s linear infinite" }}>⏳</span>
                  <span>Verifying official ICAR & Agmarknet sources in your regional language...</span>
                </div>
              </div>
            </div>
          )}

          {errorMessage && (
            <div className="auth-error-alert" style={{ margin: "10px 0" }}>
              <span>⚠️</span>
              <span>{errorMessage}</span>
            </div>
          )}

          <div ref={chatBottomRef} />
        </div>

        {/* Bottom Sticky Composer */}
        <div className="bottom-composer-bar">
          {isRecording && (
            <div className="recording-indicator-bar">
              <span>🔴</span>
              <span>Recording voice in {currentLangConfig.label} ({recordingSeconds}s)...</span>
            </div>
          )}

          {/* Text Input Wrapper */}
          <div className="composer-input-wrapper">
            <input
              type="text"
              className="composer-text-input"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submitQuery(textInput, "text");
                }
              }}
              placeholder={`Ask in ${currentLangConfig.label} (e.g. mandi price, pest, seed, fertilizer)...`}
              disabled={isLoading || isRecording}
            />

            <button
              className="btn-send-text"
              onClick={() => submitQuery(textInput, "text")}
              disabled={!textInput.trim() || isLoading}
              aria-label="Send message"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>

          {/* Large Voice Microphone Button (>= 56px) */}
          <button
            className={`btn-voice-mic ${isRecording ? "recording" : ""}`}
            onClick={isRecording ? stopRecording : startRecording}
            aria-label={isRecording ? "Stop voice recording" : "Start voice recording"}
            title={isRecording ? "Click to stop recording" : `Speak in ${currentLangConfig.label}`}
          >
            {isRecording ? "⏹" : "🎤"}
          </button>
        </div>
      </main>
    </div>
  );
}
