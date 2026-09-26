"use client";

import React, { useState, useEffect, useRef } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

const SUPPORTED_LANGUAGES = [
  { code: "hi-IN", label: "हिंदी (Hindi)" },
  { code: "te-IN", label: "తెలుగు (Telugu)" },
  { code: "ta-IN", label: "தமிழ் (Tamil)" },
  { code: "mr-IN", label: "मराठी (Marathi)" },
  { code: "kn-IN", label: "ಕನ್ನಡ (Kannada)" },
  { code: "en-IN", label: "English" },
  { code: "bn-IN", label: "বাংলা (Bengali)" },
  { code: "gu-IN", label: "ગુજરાતી (Gujarati)" },
  { code: "pa-IN", label: "ਪੰਜਾਬੀ (Punjabi)" },
];

export type AppState =
  | "IDLE"
  | "RECORDING"
  | "UPLOADING"
  | "TRANSCRIBING"
  | "READY_TO_ASK"
  | "THINKING"
  | "ANSWER_READY"
  | "SPEAKING"
  | "ERROR"
  | "TEXT_INPUT"
  | "SUBMITTING_TEXT";

interface FarmerContext {
  state: string;
  district: string;
  crops: string;
}

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
  createdAt: string;
}

export default function FarmerAdvisorPage() {
  const [selectedLanguage, setSelectedLanguage] = useState("hi-IN");
  const [appState, setAppState] = useState<AppState>("IDLE");
  const [textInput, setTextInput] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [ttsNotice, setTtsNotice] = useState<string | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);

  // Conversation tracking
  const [conversationId, setConversationId] = useState<string>("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);

  // Farmer context (local storage backed)
  const [farmerContext, setFarmerContext] = useState<FarmerContext>({
    state: "Madhya Pradesh",
    district: "Indore",
    crops: "Wheat",
  });
  const [isContextDrawerOpen, setIsContextDrawerOpen] = useState(false);

  // Audio refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const chatBottomRef = useRef<HTMLDivElement | null>(null);

  // Initialize conversation and context from storage
  useEffect(() => {
    const storedConv = sessionStorage.getItem("farmer_conv_id");
    if (storedConv) {
      setConversationId(storedConv);
    } else {
      const newId = crypto.randomUUID();
      sessionStorage.setItem("farmer_conv_id", newId);
      setConversationId(newId);
    }

    try {
      const storedCtx = localStorage.getItem("farmer_profile_context");
      if (storedCtx) {
        setFarmerContext(JSON.parse(storedCtx));
      }
    } catch {
      // Ignore JSON parse error
    }
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, appState]);

  // Clean up audio on unmount
  useEffect(() => {
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (activeAudioRef.current) {
        activeAudioRef.current.pause();
        activeAudioRef.current = null;
      }
    };
  }, []);

  // Save farmer context
  const handleSaveContext = (updated: FarmerContext) => {
    setFarmerContext(updated);
    localStorage.setItem("farmer_profile_context", JSON.stringify(updated));
    setIsContextDrawerOpen(false);
  };

  // ----------------------------------------------------
  // Voice Recording Pipeline
  // ----------------------------------------------------
  const startRecording = async () => {
    // FSM guard: cannot record while uploading, thinking, or already recording
    if (["RECORDING", "UPLOADING", "TRANSCRIBING", "THINKING", "SUBMITTING_TEXT"].includes(appState)) {
      return;
    }

    setErrorMessage(null);
    setTtsNotice(null);

    // Stop speaking audio if active
    if (activeAudioRef.current) {
      activeAudioRef.current.pause();
      activeAudioRef.current = null;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];

      let mimeType = "audio/webm";
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        mimeType = "audio/webm;codecs=opus";
      } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
        mimeType = "audio/mp4";
      } else if (MediaRecorder.isTypeSupported("audio/ogg")) {
        mimeType = "audio/ogg";
      }

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const finalMime = recorder.mimeType || mimeType;
        handleUploadAndTranscribe(finalMime);
      };

      recorder.start(250);
      setAppState("RECORDING");
      setRecordingSeconds(0);

      timerIntervalRef.current = setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev >= 59) {
            stopRecording();
            return 60;
          }
          return prev + 1;
        });
      }, 1000);
    } catch (err: any) {
      console.error("Microphone access failed:", err);
      setAppState("ERROR");
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        setErrorMessage("Microphone permission denied. Please allow microphone access or type your question below.");
      } else {
        setErrorMessage("Microphone unavailable: " + (err.message || "Unknown error"));
      }
    }
  };

  const stopRecording = () => {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      setAppState("UPLOADING");
      mediaRecorderRef.current.stop();
    }
  };

  const handleMicToggle = () => {
    if (appState === "RECORDING") {
      stopRecording();
    } else {
      startRecording();
    }
  };

  // Upload audio to STT
  const handleUploadAndTranscribe = async (mimeType: string) => {
    setAppState("TRANSCRIBING");
    try {
      const actualMimeType = mediaRecorderRef.current?.mimeType || mimeType;
      const audioBlob = new Blob(audioChunksRef.current, { type: actualMimeType });
      if (audioBlob.size === 0) {
        throw new Error("Recorded voice audio was empty.");
      }

      const formData = new FormData();
      const ext = actualMimeType.includes("mp4") ? "m4a" : actualMimeType.includes("ogg") ? "ogg" : "webm";
      formData.append("audio_file", audioBlob, `voice_query.${ext}`);
      formData.append("language", selectedLanguage);

      const response = await fetch(`${BACKEND_URL}/api/v1/voice/stt`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        // Log the raw backend diagnostic for developers; never surface to farmer.
        const technicalDetail = errorData.detail?.message || errorData.detail || "STT provider error";
        console.error("STT backend error detail:", technicalDetail);
        throw new Error("VOICE_ERROR");
      }

      const result = await response.json();
      const transcript = result.transcript;
      setTextInput(transcript);
      setAppState("READY_TO_ASK");

      // Seamless auto-transition to advisor query for natural voice interaction
      submitAdvisorQuery(transcript, "voice");
    } catch (err: any) {
      console.error("STT Error:", err);
      setAppState("ERROR");
      // Always show a farmer-friendly message; never expose technical/backend error details.
      setErrorMessage("Sorry, I couldn't process that voice recording. Please try again, or type your question below.");
    }
  };

  // ----------------------------------------------------
  // Advisor Query Pipeline (Voice & Text Convergence)
  // ----------------------------------------------------
  const submitAdvisorQuery = async (queryText: string, channel: "voice" | "text") => {
    const trimmed = queryText.trim();
    if (!trimmed) return;

    // FSM guard: cannot submit while thinking or recording
    if (["THINKING", "RECORDING", "UPLOADING"].includes(appState)) return;

    setAppState("THINKING");
    setErrorMessage(null);
    setTtsNotice(null);

    // Append user question to conversation thread
    const userMsgId = crypto.randomUUID();
    const userMessage: ConversationMessage = {
      id: userMsgId,
      role: "user",
      text: trimmed,
      language: selectedLanguage,
      inputChannel: channel,
      createdAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((prev) => [...prev, userMessage]);
    setTextInput("");

    try {
      const payload = {
        query: trimmed,
        language: selectedLanguage,
        input_channel: channel,
        conversation_id: conversationId || undefined,
        farmer_context: {
          state: farmerContext.state || undefined,
          district: farmerContext.district || undefined,
          crop: farmerContext.crops || undefined,
          language: selectedLanguage,
        },
      };

      const response = await fetch(`${BACKEND_URL}/api/v1/advisor/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || "Failed to reach Agricultural Advisor.");
      }

      const data = await response.json();

      // Update conversation_id if newly returned
      if (data.conversation_id && data.conversation_id !== conversationId) {
        setConversationId(data.conversation_id);
        sessionStorage.setItem("farmer_conv_id", data.conversation_id);
      }

      const advisorMessage: ConversationMessage = {
        id: data.query_id || crypto.randomUUID(),
        role: "advisor",
        text: data.response_text,
        language: data.language,
        intent: data.intent,
        inputChannel: channel,
        extractedContext: data.extracted_context,
        inheritedContext: data.inherited_context,
        citations: data.citations,
        dataOrigin: data.data_origin,
        isGrounded: data.is_grounded,
        abstained: data.abstained,
        abstentionReason: data.abstention_reason,
        llmCalled: data.llm_called,
        createdAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, advisorMessage]);
      setAppState("ANSWER_READY");

      // Auto-trigger voice synthesis if submitted via voice
      if (channel === "voice" && !data.abstained) {
        handleSpeakText(data.response_text);
      }
    } catch (err: any) {
      console.error("Advisor Error:", err);
      setAppState("ERROR");
      setErrorMessage(err.message || "Advisor service temporarily unavailable. Please try again.");
    }
  };

  // ----------------------------------------------------
  // Text-to-Speech (TTS) Voice Synthesis
  // ----------------------------------------------------
  const handleSpeakText = async (textToSpeak: string) => {
    if (!textToSpeak.trim()) return;

    // Stop current audio if playing
    if (activeAudioRef.current) {
      activeAudioRef.current.pause();
      activeAudioRef.current = null;
    }

    setTtsNotice(null);
    setAppState("SPEAKING");

    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/voice/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: textToSpeak,
          language: selectedLanguage,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const msg = errorData.detail?.message || errorData.detail || "Voice playback unavailable.";
        throw new Error(msg);
      }

      const result = await response.json();
      const audioUrl = `data:audio/wav;base64,${result.audio_base64}`;

      const audio = new Audio(audioUrl);
      activeAudioRef.current = audio;

      audio.onplay = () => {
        setAppState("SPEAKING");
      };

      audio.onended = () => {
        setAppState("ANSWER_READY");
      };

      audio.onerror = () => {
        setAppState("ANSWER_READY");
        setTtsNotice("Audio playback failed in browser. You can read the verified advice above.");
      };

      await audio.play();
    } catch (err: any) {
      console.warn("TTS Notice:", err);
      // Critical requirement: TTS failure must NOT destroy textual response
      setAppState("ANSWER_READY");
      setTtsNotice("Voice playback temporarily unavailable. Please read the verified advice above.");
    }
  };

  const handleStopSpeaking = () => {
    if (activeAudioRef.current) {
      activeAudioRef.current.pause();
      activeAudioRef.current = null;
    }
    setAppState("ANSWER_READY");
  };

  const handleStartNewChat = () => {
    const newId = crypto.randomUUID();
    sessionStorage.setItem("farmer_conv_id", newId);
    setConversationId(newId);
    setMessages([]);
    setTextInput("");
    setAppState("IDLE");
    setErrorMessage(null);
    setTtsNotice(null);
  };

  return (
    <div className="farmer-app-root">
      {/* ----------------- TOP HEADER: LANGUAGE & FARMER CONTEXT ----------------- */}
      <header className="farmer-header">
        <div className="header-brand">
          <div className="brand-leaf-icon">🌾</div>
          <div>
            <h1 className="brand-heading">Kisan AI Advisor</h1>
            <p className="brand-subtext">Official Government & ICAR Knowledge</p>
          </div>
        </div>

        <div className="header-actions">
          {/* Language Selector Dropdown */}
          <select
            className="language-dropdown"
            value={selectedLanguage}
            onChange={(e) => setSelectedLanguage(e.target.value)}
            disabled={["RECORDING", "UPLOADING", "TRANSCRIBING", "THINKING"].includes(appState)}
            aria-label="Select Language"
          >
            {SUPPORTED_LANGUAGES.map((lang) => (
              <option key={lang.code} value={lang.code}>
                {lang.label}
              </option>
            ))}
          </select>

          {/* Farmer Profile Context Button */}
          <button
            className="context-badge-btn"
            onClick={() => setIsContextDrawerOpen(true)}
            title="Farm Context"
            aria-label="Edit Farm Context"
          >
            📍 {farmerContext.district || "Farm"}
          </button>
        </div>
      </header>

      {/* ----------------- CONTEXT DRAWER / MODAL ----------------- */}
      {isContextDrawerOpen && (
        <div className="modal-backdrop" onClick={() => setIsContextDrawerOpen(false)}>
          <div className="context-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>🌾 Farm Context (मेरा खेत)</h3>
              <button className="close-btn" onClick={() => setIsContextDrawerOpen(false)}>
                ✕
              </button>
            </div>
            <p className="modal-subtitle">
              Used to personalize local mandi prices and crop advisories without collecting sensitive data.
            </p>

            <div className="form-group">
              <label>State (राज्य)</label>
              <input
                type="text"
                value={farmerContext.state}
                onChange={(e) => setFarmerContext({ ...farmerContext, state: e.target.value })}
                placeholder="e.g. Madhya Pradesh, Punjab, Telangana"
              />
            </div>

            <div className="form-group">
              <label>District / Mandi Market (ज़िला / मंडी)</label>
              <input
                type="text"
                value={farmerContext.district}
                onChange={(e) => setFarmerContext({ ...farmerContext, district: e.target.value })}
                placeholder="e.g. Indore, Ludhiana, Warangal"
              />
            </div>

            <div className="form-group">
              <label>Active Crop(s) (फसलें)</label>
              <input
                type="text"
                value={farmerContext.crops}
                onChange={(e) => setFarmerContext({ ...farmerContext, crops: e.target.value })}
                placeholder="e.g. Wheat, Paddy, Cotton"
              />
            </div>

            <div className="modal-actions">
              <button
                className="primary-action-btn"
                onClick={() => handleSaveContext(farmerContext)}
              >
                Save Farm Context
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ----------------- MAIN CONVERSATION THREAD ----------------- */}
      <main className="conversation-container">
        {messages.length === 0 && (
          <div className="empty-conversation-guide">
            <div className="guide-icon">🎙️</div>
            <h2>Speak or Type Your Agricultural Question</h2>
            <p className="guide-subtext">
              Ask about pest control, fertilizer recommendations, verified mandi prices, or government schemes.
            </p>

            <div className="suggestion-pills">
              <button
                onClick={() => {
                  setTextInput("What is the wheat price in Indore mandi?");
                  setAppState("TEXT_INPUT");
                }}
              >
                🌾 Wheat price in Indore mandi
              </button>
              <button
                onClick={() => {
                  setTextInput("How to control yellow stem borer in paddy?");
                  setAppState("TEXT_INPUT");
                }}
              >
                🐛 Yellow stem borer in paddy
              </button>
              <button
                onClick={() => {
                  setTextInput("Who is eligible for PM-KISAN scheme?");
                  setAppState("TEXT_INPUT");
                }}
              >
                📋 PM-KISAN eligibility criteria
              </button>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`message-row ${msg.role === "user" ? "user-row" : "advisor-row"}`}>
            {msg.role === "user" ? (
              <div className="user-bubble">
                <div className="user-meta">
                  <span>{msg.inputChannel === "voice" ? "🎙️ Voice Query" : "⌨️ Text Query"}</span>
                  <span>{msg.createdAt}</span>
                </div>
                <p className="user-text">{msg.text}</p>
              </div>
            ) : (
              <div className="advisor-card">
                <div className="card-top-bar">
                  <div className="authority-pill">
                    {msg.abstained ? (
                      <span className="badge-abstain">⚠️ Safe Abstention</span>
                    ) : msg.dataOrigin === "production_live" ? (
                      <span className="badge-live">🟢 Official source • Latest available daily data</span>
                    ) : (
                      <span className="badge-cached">🔵 Official source • Cached data</span>
                    )}
                  </div>
                  <span className="timestamp">{msg.createdAt}</span>
                </div>

                <div className="advisor-answer-body">
                  <p className="formatted-answer">{msg.text}</p>
                </div>

                {/* Audio Listen Action */}
                {!msg.abstained && (
                  <div className="audio-actions">
                    {appState === "SPEAKING" ? (
                      <button className="listen-btn speaking" onClick={handleStopSpeaking}>
                        ⏸️ Pause Audio (रोकें)
                      </button>
                    ) : (
                      <button
                        className="listen-btn"
                        onClick={() => handleSpeakText(msg.text)}
                        disabled={["RECORDING", "UPLOADING", "THINKING"].includes(appState)}
                      >
                        🔊 Listen in {selectedLanguage.split("-")[0].toUpperCase()} (सुनें)
                      </button>
                    )}
                  </div>
                )}

                {/* Citations List */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="citations-tray">
                    <span className="citations-header">Verified Sources:</span>
                    <div className="citation-chips">
                      {msg.citations.map((c, idx) => (
                        <div key={idx} className="citation-chip">
                          <span className="citation-title">{c.title}</span>
                          <span className="citation-authority">• {c.issuing_authority}</span>
                          {c.official_url && (
                            <a
                              href={c.official_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="raw-url-link"
                              title={c.official_url}
                            >
                              🔗 Portal
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Compact Expandable Diagnostic Details */}
                {(msg.intent || msg.inheritedContext) && (
                  <details className="diagnostic-expander">
                    <summary>Technical & Provenance Trace</summary>
                    <div className="diagnostic-body">
                      <div><strong>Intent:</strong> {msg.intent || "CROP_ADVISORY"}</div>
                      {msg.extractedContext && Object.keys(msg.extractedContext).length > 0 && (
                        <div><strong>Extracted:</strong> {JSON.stringify(msg.extractedContext)}</div>
                      )}
                      {msg.inheritedContext && Object.keys(msg.inheritedContext).length > 0 && (
                        <div><strong>Inherited Context:</strong> {JSON.stringify(msg.inheritedContext)}</div>
                      )}
                      <div><strong>LLM Generated:</strong> {msg.llmCalled ? "YES" : "NO (Deterministic Format)"}</div>
                      <div><strong>Grounding Verified:</strong> {msg.isGrounded ? "YES" : "NO"}</div>
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Live Processing States */}
        {appState === "UPLOADING" && (
          <div className="state-status-pill">
            <span className="pulse-dot green" /> Uploading voice recording...
          </div>
        )}
        {appState === "TRANSCRIBING" && (
          <div className="state-status-pill">
            <span className="pulse-dot green" /> Transcribing with Sarvam AI...
          </div>
        )}
        {appState === "THINKING" && (
          <div className="state-status-pill">
            <span className="pulse-dot green" /> Checking official agricultural sources...
          </div>
        )}

        {/* Actionable Error & Notice Bars */}
        {errorMessage && (
          <div className="error-banner">
            <span>⚠️ {errorMessage}</span>
            <button className="dismiss-btn" onClick={() => setErrorMessage(null)}>✕</button>
          </div>
        )}
        {ttsNotice && (
          <div className="notice-banner">
            <span>ℹ️ {ttsNotice}</span>
            <button className="dismiss-btn" onClick={() => setTtsNotice(null)}>✕</button>
          </div>
        )}

        <div ref={chatBottomRef} />
      </main>

      {/* ----------------- BOTTOM CONTROLS: MIC & TEXT INPUT ----------------- */}
      <footer className="farmer-controls">
        {/* Large Primary Microphone with State Rings */}
        <div className="mic-center-wrapper">
          <button
            className={`large-mic-btn ${appState === "RECORDING" ? "recording" : ""}`}
            onClick={handleMicToggle}
            disabled={["UPLOADING", "TRANSCRIBING", "THINKING", "SUBMITTING_TEXT"].includes(appState)}
            aria-label={appState === "RECORDING" ? "Stop Recording" : "Start Voice Recording"}
          >
            {appState === "RECORDING" ? (
              <span className="mic-icon stop">⏹</span>
            ) : (
              <span className="mic-icon">🎙️</span>
            )}
          </button>

          <span className="mic-label">
            {appState === "RECORDING" ? (
              <strong className="recording-timer">Recording: {recordingSeconds}s (Tap to Send)</strong>
            ) : appState === "TRANSCRIBING" ? (
              "Transcribing..."
            ) : appState === "THINKING" ? (
              "Verifying advice..."
            ) : (
              "Tap Mic to Speak"
            )}
          </span>
        </div>

        {/* Text Fallback Input Bar */}
        <form
          className="text-input-bar"
          onSubmit={(e) => {
            e.preventDefault();
            submitAdvisorQuery(textInput, "text");
          }}
        >
          <input
            type="text"
            className="query-input"
            value={textInput}
            onChange={(e) => {
              setTextInput(e.target.value);
              if (appState === "IDLE" || appState === "ANSWER_READY") {
                setAppState("TEXT_INPUT");
              }
            }}
            placeholder="Type question or speak with mic above..."
            disabled={["RECORDING", "UPLOADING", "TRANSCRIBING", "THINKING"].includes(appState)}
          />
          <button
            type="submit"
            className="send-btn"
            disabled={!textInput.trim() || ["RECORDING", "UPLOADING", "TRANSCRIBING", "THINKING"].includes(appState)}
            aria-label="Send Query"
          >
            Ask ➔
          </button>

          {messages.length > 0 && (
            <button
              type="button"
              className="new-chat-btn"
              onClick={handleStartNewChat}
              title="Start New Conversation"
            >
              🔄
            </button>
          )}
        </form>
      </footer>
    </div>
  );
}
