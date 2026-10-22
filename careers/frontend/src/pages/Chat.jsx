import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  FileText,
  Film,
  Folder,
  Image as ImageIcon,
  Link2,
  Loader2,
  MessageCircle,
  MoreVertical,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
  Send,
  Smile,
  UserPlus,
  UsersRound,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  createChatSocket,
  createChatGroup,
  getCurrentChatUser,
  getChatGroups,
  getChatUsers,
  getDirectMessages,
  getGroupMessages,
  sendDirectMessage,
  sendGroupMessage
} from "../api/chat";
import { Alert } from "../components/Alert";
import { CandidateSpinner, cx } from "../components/candidate/CandidateUI";
import { useAuth } from "../context/AuthContext";
import {
  CHAT_MAX_ATTACHMENTS,
  chatGroupSchema,
  chatMessageSchema,
  clearFieldError,
  fieldError,
  formatFileSize,
  validateChatFile,
  validateForm
} from "../validation/forms";

function getInitials(value) {
  const parts = String(value || "User")
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2);
  return parts.map((part) => part.charAt(0).toUpperCase()).join("") || "U";
}

function avatarUrlFor(seed) {
  return `https://api.dicebear.com/8.x/initials/svg?seed=${encodeURIComponent(seed || "User")}`;
}

function formatMessageTime(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function normalizeChannelText(channel) {
  return `${channel.title} ${channel.subtitle || ""} ${channel.preview || ""}`.toLowerCase();
}

function getUserDisplayName(user) {
  return user?.displayName || user?.full_name || user?.username || user?.email?.split("@")[0] || "Candidate";
}

function directUserKey(user) {
  return String(user?.appUserId || user?.email || getUserDisplayName(user) || user?._id || user?.id)
    .normalize("NFC")
    .toLowerCase();
}

function displayNameScore(user) {
  const name = getUserDisplayName(user);
  let score = 0;
  if (user?.displayName || user?.full_name) score += 4;
  if (/[^\x00-\x7F]/.test(name)) score += 3;
  if (!/-/.test(name)) score += 1;
  if (user?.updatedAt) score += 1;
  return score;
}

function dedupeUsers(users) {
  const byKey = new Map();
  users.forEach((user) => {
    const key = directUserKey(user);
    const current = byKey.get(key);
    if (!current || displayNameScore(user) >= displayNameScore(current)) {
      byKey.set(key, user);
    }
  });
  return [...byKey.values()];
}

function getChatErrorMessage(error) {
  const status = error?.response?.status;
  const data = error?.response?.data;

  if (status === 401) {
    return "Chat service could not validate this session. Restart chat-service after the latest update, then sign in again if needed.";
  }
  if (typeof data?.message === "string") return data.message;
  if (typeof data?.detail === "string") return data.detail;
  return error?.message || "Chat service is not reachable.";
}

const STATUS_OPTIONS = [
  { value: "available", label: "available", dot: "bg-[#10b981]" },
  { value: "busy", label: "busy", dot: "bg-[#ef4444]" },
  { value: "away", label: "away", dot: "bg-[#f59e0b]" }
];

const EMOJI_OPTIONS = ["😀", "😊", "🔥", "👏", "💡", "✅", "🎯", "🙌"];

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function createClientMessageId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function extractLinks(text) {
  return String(text || "").match(/https?:\/\/[^\s)]+/g) || [];
}

function isDocumentLink(value) {
  return /\.(pdf|docx?|xlsx?|pptx?|txt)(\?|#|$)/i.test(value || "");
}

function attachmentUrl(attachment) {
  return attachment?.url || attachment?.dataUrl || attachment?.href || "";
}

function attachmentContentType(attachment) {
  return attachment?.contentType || attachment?.type || "";
}

function attachmentKind(attachment) {
  const contentType = attachmentContentType(attachment);
  const name = attachment?.name || attachment?.fileName || attachmentUrl(attachment);
  if (contentType.startsWith("image/") || /\.(png|jpe?g|gif|webp)(\?|#|$)/i.test(name)) return "photos";
  if (contentType.startsWith("video/") || /\.(mp4|mov|webm)(\?|#|$)/i.test(name)) return "movies";
  if (isDocumentLink(name) || isDocumentLink(attachmentUrl(attachment))) return "documents";
  return "other";
}

function attachmentTitle(attachment) {
  return attachment?.name || (attachmentKind(attachment) === "photos" ? "Image attachment" : "Shared file");
}

function messagePreviewText(message, fallback = "Group room") {
  if (message?.text) return message.text;
  if (Array.isArray(message?.attachments) && message.attachments.length > 0) {
    return message.attachments.length === 1 ? attachmentTitle(message.attachments[0]) : `${message.attachments.length} attachments`;
  }
  if (message?.image) return "Image attachment";
  return fallback;
}

function buildSharedItems(messages) {
  return messages.flatMap((message) => {
    const createdAt = message.createdAt || message.timestamp;
    const items = [];
    const messageAttachments = Array.isArray(message.attachments) ? message.attachments : [];
    messageAttachments.forEach((attachment, index) => {
      items.push({
        id: `${message._id || message.clientMessageId || createdAt}-attachment-${index}`,
        kind: attachmentKind(attachment),
        title: attachmentTitle(attachment),
        detail: attachment.size ? formatFileSize(Number(attachment.size)) : formatMessageTime(createdAt) || "recent",
        href: attachmentUrl(attachment)
      });
    });

    if (message.image && messageAttachments.length === 0) {
      items.push({
        id: `${message._id || createdAt}-image`,
        kind: "photos",
        title: "Image attachment",
        detail: formatMessageTime(createdAt) || "recent",
        href: message.image
      });
    }

    extractLinks(message.text).forEach((link, index) => {
      items.push({
        id: `${message._id || createdAt}-link-${index}`,
        kind: isDocumentLink(link) ? "documents" : "links",
        title: isDocumentLink(link) ? "Document link" : "Shared link",
        detail: link.replace(/^https?:\/\//, ""),
        href: link
      });
    });

    return items;
  });
}

function buildChannels(users, groups, unseenMessages) {
  const groupChannels = groups.map((group) => ({
    id: group._id,
    type: "group",
    title: group.name,
    subtitle: group.description || `${group.members?.length || 0} members`,
    preview: messagePreviewText(group.lastMessage, "Group room"),
    avatar: group.avatar,
    unread: 0,
    members: group.members || [],
    updatedAt: group.updatedAt || group.createdAt,
    meta: "Group"
  }));

  const directChannels = dedupeUsers(users).map((user) => ({
    id: user._id,
    type: "direct",
    title: getUserDisplayName(user),
    subtitle: user.bio || user.email || "Direct message",
    preview: "Open the conversation",
    avatar: user.profilePicture,
    unread: unseenMessages?.[user._id] || 0,
    members: [],
    updatedAt: user.updatedAt || user.createdAt,
    meta: "Direct"
  }));

  return [...groupChannels, ...directChannels];
}

function isOwnMessage(message, activeChannel, user) {
  if (!message) return false;
  if (activeChannel?.type === "direct") {
    const receiverId = typeof message.receiver === "object" ? message.receiver?._id : message.receiver;
    return receiverId === activeChannel.id;
  }

  const sender = message.sender;
  if (!sender) return false;
  const senderAppUserId = typeof sender === "object" ? sender.appUserId : "";
  const senderEmail = typeof sender === "object" ? sender.email : "";
  return senderAppUserId === `fastapi:${user?.id}` || senderEmail === user?.email;
}

function messageId(message) {
  return message?._id || message?.id || `${message?.createdAt || message?.timestamp || ""}-${message?.text || ""}`;
}

function isSameMessage(left, right) {
  const leftClientId = left?.clientMessageId;
  const rightClientId = right?.clientMessageId;
  if (leftClientId && rightClientId && leftClientId === rightClientId) return true;
  return messageId(left) === messageId(right);
}

function appendUniqueMessage(messages, nextMessage) {
  const existingIndex = messages.findIndex((message) => isSameMessage(message, nextMessage));
  if (existingIndex < 0) return [...messages, nextMessage];
  return messages.map((message, index) => (
    index === existingIndex
      ? { ...message, ...nextMessage, __status: nextMessage.__status, __error: nextMessage.__error, __retryPayload: nextMessage.__retryPayload }
      : message
  ));
}

function getMessagePartyId(value) {
  if (!value) return "";
  return typeof value === "object" ? String(value._id || value.id || value.appUserId || value.email || "") : String(value);
}

function messageBelongsToChannel(message, activeChannel) {
  if (!message || !activeChannel) return false;
  if (activeChannel.type === "group") {
    return getMessagePartyId(message.group) === String(activeChannel.id);
  }
  const senderId = getMessagePartyId(message.sender);
  const receiverId = getMessagePartyId(message.receiver);
  return senderId === String(activeChannel.id) || receiverId === String(activeChannel.id);
}

function ChatAvatar({ title, image, className }) {
  if (image) {
    return <img src={image} alt="" className={cx("shrink-0 rounded-full object-cover", className)} />;
  }

  return (
    <span className={cx("flex shrink-0 items-center justify-center rounded-full bg-[#eaf7fd] text-xs font-extrabold text-[var(--candidate-primary)]", className)}>
      {getInitials(title)}
    </span>
  );
}

function ProfileHeader({ user, status, statusOpen, onToggleStatus, onStatusChange, onBack }) {
  const displayName = user?.full_name || user?.email?.split("@")[0] || "Workspace user";
  const activeStatus = STATUS_OPTIONS.find((item) => item.value === status) || STATUS_OPTIONS[0];

  return (
    <div className="px-5 pb-5 pt-4">
      <div className="mb-5 flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#f3f6f8] text-[#9aa7b5] transition hover:bg-[#eaf7fd] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#bde9fb]"
          aria-label="Back"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </button>
        <h1 className="text-lg font-extrabold text-[#17202a]">Chat</h1>
      </div>

      <div className="grid justify-items-center">
        <div className="relative">
          <ChatAvatar title={displayName} image={avatarUrlFor(displayName)} className="h-20 w-20" />
          <span className={cx("absolute bottom-1 right-1 h-3 w-3 rounded-full border-2 border-white", activeStatus.dot)} />
        </div>
        <p className="mt-3 max-w-[12rem] truncate text-center text-lg font-extrabold text-[#18212d]">{displayName}</p>
        <div className="relative mt-2">
          <button
            type="button"
            onClick={onToggleStatus}
            className="inline-flex min-h-7 items-center gap-1 rounded-lg bg-[#eaf7fd] px-3 text-xs font-extrabold text-[var(--candidate-primary)]"
            aria-expanded={statusOpen}
          >
            {activeStatus.label}
            <ChevronRight className={cx("h-3 w-3 transition", statusOpen ? "-rotate-90" : "rotate-90")} aria-hidden="true" />
          </button>
          {statusOpen && (
            <div className="absolute left-1/2 z-30 mt-2 w-36 -translate-x-1/2 rounded-xl border border-[#dfe7ee] bg-white p-1 shadow-xl">
              {STATUS_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onStatusChange(option.value)}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-extrabold text-[#18212d] hover:bg-[#f3f6f8]"
                >
                  <span className={cx("h-2.5 w-2.5 rounded-full", option.dot)} />
                  {option.label}
                  {status === option.value && <Check className="ml-auto h-3.5 w-3.5 text-[var(--candidate-primary)]" aria-hidden="true" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ChannelRow({ channel, active, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(channel)}
      className={cx(
        "grid w-full grid-cols-[2.4rem_minmax(0,1fr)_auto] items-center gap-3 rounded-xl px-3 py-3 text-left transition",
        "hover:bg-[#f3f6f8] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#bde9fb]",
        active && "bg-[#f1f4f7]"
      )}
    >
      <ChatAvatar title={channel.title} image={channel.avatar} className="h-9 w-9" />
      <span className="min-w-0">
        <span className="block truncate text-sm font-extrabold text-[#18212d]">{channel.title}</span>
        <span className="mt-0.5 block truncate text-xs font-semibold text-[#9aa7b5]">{channel.preview || channel.subtitle}</span>
      </span>
      <span className="flex flex-col items-end gap-1">
        <span className="text-[0.68rem] font-bold text-[#9aa7b5]">{formatMessageTime(channel.updatedAt) || "now"}</span>
        {channel.unread > 0 && (
          <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--candidate-primary)] px-1.5 text-[0.68rem] font-extrabold text-white">
            {channel.unread}
          </span>
        )}
      </span>
    </button>
  );
}

function ConversationPanel({
  user,
  query,
  setQuery,
  channels,
  activeChannel,
  onSelect,
  loading,
  status,
  statusOpen,
  onToggleStatus,
  onStatusChange,
  onBack,
  onOpenNewChat,
  actionsOpen,
  onToggleActions,
  onRefresh,
  channelFilter,
  onChannelFilterChange
}) {
  return (
    <aside className="h-full min-h-0 min-w-0 overflow-y-auto border-b border-[#e7ebf1] bg-white lg:border-b-0 lg:border-r">
      <ProfileHeader
        user={user}
        status={status}
        statusOpen={statusOpen}
        onToggleStatus={onToggleStatus}
        onStatusChange={onStatusChange}
        onBack={onBack}
      />

      <div className="px-5 pb-4">
        <label className="relative block">
          <span className="sr-only">Search chats</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search"
            maxLength={80}
            className="h-10 w-full rounded-lg border-0 bg-[#f1f4f7] px-4 pr-10 text-sm font-semibold text-[#18212d] outline-none placeholder:text-[#b0bac5] focus:ring-4 focus:ring-[#bde9fb]"
          />
          <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9aa7b5]" aria-hidden="true" />
        </label>

        <div className="mt-5 flex items-center justify-between">
          <p className="text-sm font-bold text-[#7d8a98]">Last chats</p>
          <div className="relative flex items-center gap-2">
            {loading && <CandidateSpinner label="" />}
            <button
              type="button"
              onClick={onOpenNewChat}
              className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#eaf7fd] text-[var(--candidate-primary)]"
              aria-label="New chat"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
            </button>
            <button type="button" onClick={onToggleActions} className="text-[#9aa7b5]" aria-label="More chat actions" aria-expanded={actionsOpen}>
              <MoreVertical className="h-4 w-4" aria-hidden="true" />
            </button>
            {actionsOpen && (
              <div className="absolute right-0 top-9 z-30 w-44 rounded-xl border border-[#dfe7ee] bg-white p-1 shadow-xl">
                <button type="button" onClick={onRefresh} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-extrabold text-[#18212d] hover:bg-[#f3f6f8]">
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  Refresh chats
                </button>
                {["all", "group", "direct"].map((filter) => (
                  <button
                    key={filter}
                    type="button"
                    onClick={() => onChannelFilterChange(filter)}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-extrabold text-[#18212d] hover:bg-[#f3f6f8]"
                  >
                    <span className="h-3.5 w-3.5" />
                    {filter === "all" ? "All chats" : filter === "group" ? "Groups only" : "Direct only"}
                    {channelFilter === filter && <Check className="ml-auto h-3.5 w-3.5 text-[var(--candidate-primary)]" aria-hidden="true" />}
                  </button>
                ))}
                <button type="button" onClick={() => setQuery("")} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-extrabold text-[#18212d] hover:bg-[#f3f6f8]">
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                  Clear search
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="mt-3 grid max-h-[16rem] gap-1 overflow-y-auto pr-1 lg:max-h-[calc(100dvh-22rem)]">
          {channels.length === 0 && !loading ? (
            <div className="rounded-xl bg-[#f1f4f7] px-4 py-8 text-center">
              <UsersRound className="mx-auto h-6 w-6 text-[var(--candidate-primary)]" aria-hidden="true" />
              <p className="mt-3 text-sm font-extrabold text-[#18212d]">No chats found</p>
            </div>
          ) : (
            channels.map((channel) => (
              <ChannelRow
                key={`${channel.type}-${channel.id}`}
                channel={channel}
                active={activeChannel?.id === channel.id && activeChannel?.type === channel.type}
                onSelect={onSelect}
              />
            ))
          )}
        </div>
      </div>
    </aside>
  );
}

function MessageAttachments({ message }) {
  const attachments = Array.isArray(message.attachments) ? message.attachments : [];
  const visibleAttachments = attachments.length
    ? attachments
    : message.image
      ? [{ name: "Image attachment", contentType: "image/jpeg", url: message.image }]
      : [];

  if (visibleAttachments.length === 0) return null;

  return (
    <div className="mt-3 grid gap-2">
      {visibleAttachments.map((attachment, index) => {
        const kind = attachmentKind(attachment);
        const href = attachmentUrl(attachment);
        const title = attachmentTitle(attachment);
        if (kind === "photos") {
          return (
            <a key={`${title}-${index}`} href={href} target="_blank" rel="noreferrer" className="block">
              <img src={href} alt={title} className="max-h-56 rounded-lg object-cover" />
            </a>
          );
        }

        return (
          <a
            key={`${title}-${index}`}
            href={href}
            target="_blank"
            rel="noreferrer"
            className="grid max-w-sm grid-cols-[2rem_minmax(0,1fr)] items-center gap-2 rounded-lg bg-white/70 px-3 py-2 text-left ring-1 ring-[#dfe7ee]"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#eaf7fd] text-[var(--candidate-primary)]">
              <FileText className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-xs font-extrabold text-[#18212d]">{title}</span>
              <span className="block text-[0.68rem] font-semibold text-[#7f8a99]">{attachment.size ? formatFileSize(Number(attachment.size)) : "Attachment"}</span>
            </span>
          </a>
        );
      })}
    </div>
  );
}

function BubbleMessage({ message, activeChannel, user, onRetry }) {
  const own = isOwnMessage(message, activeChannel, user);
  const sender = typeof message.sender === "object" ? message.sender : null;
  const label = own ? "You" : sender?.username || activeChannel?.title || "Teammate";
  const status = message.__status;

  return (
    <div className={cx("flex items-end gap-3", own ? "justify-end" : "justify-start")}>
      {!own && <ChatAvatar title={label} image={sender?.profilePicture} className="h-7 w-7" />}
      <div className={cx("max-w-[78%]", own && "text-right")}>
        <p className="mb-1 text-[0.68rem] font-bold text-[#7f8a99]">
          {own ? "You" : label}, {formatMessageTime(message.createdAt || message.timestamp)}
        </p>
        <div className={cx("rounded-xl px-4 py-3 text-sm font-semibold leading-6 shadow-sm", own ? "rounded-br-md bg-[#d9edf9] text-[#102a43]" : "rounded-bl-md bg-white text-[#253044]")}>
          {message.text && <p className="whitespace-pre-wrap break-words">{message.text}</p>}
          <MessageAttachments message={message} />
        </div>
        {status && (
          <div className={cx("mt-1 flex items-center gap-2 text-[0.68rem] font-bold", own ? "justify-end" : "justify-start")}>
            {status === "sending" && (
              <span className="inline-flex items-center gap-1 text-[#7f8a99]">
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                Sending
              </span>
            )}
            {status === "failed" && (
              <>
                <span className="text-rose-600">{message.__error || "Failed to send"}</span>
                <button type="button" onClick={() => onRetry(message)} className="text-[var(--candidate-primary)] underline-offset-2 hover:underline">
                  Retry
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ParticipantsView({ activeChannel }) {
  const members = activeChannel?.type === "group" ? activeChannel.members || [] : activeChannel ? [activeChannel] : [];

  return (
    <div className="grid gap-3">
      {members.length === 0 ? (
        <div className="rounded-xl bg-white px-4 py-8 text-center">
          <UsersRound className="mx-auto h-8 w-8 text-[var(--candidate-primary)]" aria-hidden="true" />
          <p className="mt-3 text-sm font-extrabold text-[#18212d]">No participants to show</p>
        </div>
      ) : (
        members.map((member) => {
          const id = member._id || member.id || member.title;
          const name = member.username || member.title || member.email || "Participant";
          return (
            <div key={id} className="grid grid-cols-[2.5rem_minmax(0,1fr)_auto] items-center gap-3 rounded-xl bg-white px-4 py-3 shadow-sm">
              <ChatAvatar title={name} image={member.profilePicture || member.avatar} className="h-10 w-10" />
              <span className="min-w-0">
                <span className="block truncate text-sm font-extrabold text-[#18212d]">{name}</span>
                <span className="block truncate text-xs font-semibold text-[#8d98a6]">{member.email || member.subtitle || "Group member"}</span>
              </span>
              <span className="rounded-lg bg-[#eaf7fd] px-2 py-1 text-[0.68rem] font-extrabold text-[var(--candidate-primary)]">
                {activeChannel?.type === "group" ? "member" : "direct"}
              </span>
            </div>
          );
        })
      )}
    </div>
  );
}

function ChatCenter({
  activeChannel,
  messages,
  loading,
  draft,
  setDraft,
  sending,
  onSend,
  user,
  endRef,
  activeTab,
  onTabChange,
  emojiOpen,
  onToggleEmoji,
  onEmojiSelect,
  onAttachClick,
  attachedFiles,
  onRemoveAttachment,
  composerError,
  sharedOpen,
  onToggleShared,
  onOpenNewChat,
  onRetryMessage
}) {
  return (
    <section className={cx("grid h-full min-h-0 min-w-0 overflow-hidden bg-[#edf8fb]", activeChannel ? "grid-rows-[auto_minmax(0,1fr)_auto]" : "grid-rows-[auto_minmax(0,1fr)]")}>
      <header className="flex items-center justify-between border-b border-[#dfe5eb] bg-[#f4f7fa] px-5 py-3">
        <div className="min-w-0">
          <p className="truncate text-base font-extrabold text-[#18212d]">
            {activeChannel ? (activeChannel.type === "direct" ? "Direct Chat" : "Group Chat") : "Chat workspace"}
          </p>
          {activeChannel && <p className="mt-1 truncate text-xs font-bold text-[#8d98a6]">{activeChannel.title}</p>}
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg bg-white/80 p-1">
            {["messages", "participants"].map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => onTabChange(tab)}
                className={cx(
                  "min-h-8 rounded-lg px-4 text-xs font-extrabold transition",
                  activeTab === tab ? "bg-[#eaf7fd] text-[var(--candidate-primary)]" : "text-[#7e8b99] hover:bg-white"
                )}
              >
                {tab === "messages" ? "Messages" : "Participants"}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onToggleShared}
            className="hidden h-8 w-8 items-center justify-center rounded-lg bg-white text-[#7e8b99] transition hover:bg-[#eaf7fd] hover:text-[var(--candidate-primary)] xl:flex"
            aria-label={sharedOpen ? "Hide shared files" : "Show shared files"}
          >
            <Folder className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="min-h-0 overflow-y-auto px-4 py-4 sm:px-6" data-chat-scroll="messages">
        {!activeChannel && (
          <div className="flex h-full items-center justify-center text-center">
            <div className="max-w-sm rounded-2xl bg-white/70 px-8 py-7 shadow-sm ring-1 ring-[#dfe7ee]">
              <UsersRound className="mx-auto h-10 w-10 text-[var(--candidate-primary)]" aria-hidden="true" />
              <p className="mt-3 text-lg font-extrabold text-[#18212d]">Select a chat</p>
              <p className="mt-2 text-sm font-semibold leading-6 text-[#7e8b99]">Pick a room from the left panel or start a new group chat.</p>
              <button
                type="button"
                onClick={onOpenNewChat}
                className="mt-5 inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-[var(--candidate-primary)] px-4 text-sm font-extrabold text-white shadow-sm transition hover:bg-[var(--candidate-primary-hover)]"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                Start chat
              </button>
            </div>
          </div>
        )}

        {activeChannel && loading && activeTab === "messages" && (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-[var(--candidate-primary)]" aria-hidden="true" />
          </div>
        )}

        {activeChannel && activeTab === "participants" && <ParticipantsView activeChannel={activeChannel} />}

        {activeChannel && activeTab === "messages" && !loading && messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <MessageCircle className="mx-auto h-9 w-9 text-[var(--candidate-primary)]" aria-hidden="true" />
              <p className="mt-3 text-lg font-extrabold text-[#18212d]">No messages yet</p>
              <p className="mt-2 text-sm font-semibold text-[#7e8b99]">Start the first message with {activeChannel.title}.</p>
            </div>
          </div>
        )}

        {activeChannel && activeTab === "messages" && !loading && messages.length > 0 && (
          <div className="space-y-5">
            {messages.map((message) => (
              <BubbleMessage
                key={message._id || message.clientMessageId || `${message.createdAt}-${message.text}`}
                message={message}
                activeChannel={activeChannel}
                user={user}
                onRetry={onRetryMessage}
              />
            ))}
            <div ref={endRef} />
          </div>
        )}
      </div>

      {activeChannel && (
      <form onSubmit={onSend} className="shrink-0 border-t border-[#dfe5eb] bg-[#edf8fb] px-4 py-3 sm:px-5">
        {attachedFiles.length > 0 && (
          <div className="mb-2 grid gap-2 sm:grid-cols-2">
            {attachedFiles.map((attachment) => (
              <div key={attachment.id} className="flex items-center gap-3 rounded-xl border border-[#dfe7ee] bg-white px-3 py-2 shadow-sm">
                {attachment.type?.startsWith("image/") ? (
                  <img src={attachment.dataUrl} alt="" className="h-12 w-12 rounded-lg object-cover" />
                ) : (
                  <span className="flex h-12 w-12 items-center justify-center rounded-lg bg-[#eaf7fd] text-[var(--candidate-primary)]">
                    <FileText className="h-5 w-5" aria-hidden="true" />
                  </span>
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-extrabold text-[#18212d]">{attachment.name}</span>
                  <span className="block text-xs font-semibold text-[#8d98a6]">{formatFileSize(attachment.size)}</span>
                </span>
                <button type="button" onClick={() => onRemoveAttachment(attachment.id)} className="flex h-8 w-8 items-center justify-center rounded-lg text-[#8d98a6] hover:bg-[#f3f6f8]" aria-label={`Remove ${attachment.name}`}>
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
        )}
        {composerError && <p className="mb-2 text-xs font-bold text-rose-600">{composerError}</p>}
        <div className="flex min-h-12 items-center gap-3 rounded-xl bg-white px-4 shadow-sm ring-1 ring-[#dfe7ee]">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            disabled={!activeChannel || sending}
            placeholder={activeChannel ? "Write your message..." : "Select a chat first"}
            rows={1}
            maxLength={2000}
            aria-invalid={Boolean(composerError) || undefined}
            className="min-h-11 min-w-0 flex-1 resize-none border-0 bg-transparent py-3 text-sm font-semibold text-[#18212d] outline-none placeholder:text-[#aab4bf]"
          />
          <button type="button" onClick={onAttachClick} className="text-[#aab4bf] transition hover:text-[var(--candidate-primary)]" aria-label="Attach file">
            <Paperclip className="h-4 w-4" aria-hidden="true" />
          </button>
          <div className="relative">
            <button type="button" onClick={onToggleEmoji} className="text-[#aab4bf] transition hover:text-[var(--candidate-primary)]" aria-label="Add reaction" aria-expanded={emojiOpen}>
            <Smile className="h-4 w-4" aria-hidden="true" />
          </button>
            {emojiOpen && (
              <div className="absolute bottom-8 right-0 z-30 grid w-44 grid-cols-4 gap-1 rounded-xl border border-[#dfe7ee] bg-white p-2 shadow-xl">
                {EMOJI_OPTIONS.map((emoji) => (
                  <button key={emoji} type="button" onClick={() => onEmojiSelect(emoji)} className="flex h-9 items-center justify-center rounded-lg text-lg hover:bg-[#f3f6f8]">
                    {emoji}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="submit"
            disabled={(!draft.trim() && attachedFiles.length === 0) || !activeChannel || sending}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--candidate-primary)] text-white transition hover:bg-[var(--candidate-primary-hover)] disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Send message"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
          </button>
        </div>
      </form>
      )}
    </section>
  );
}

function SharedFilesPanel({ activeChannel, messages, filter, onFilterChange, onCollapse, onNotice }) {
  const memberCount = activeChannel?.type === "group" ? activeChannel.members?.length || 0 : activeChannel ? 2 : 0;
  const sharedItems = useMemo(() => buildSharedItems(messages), [messages]);
  const counts = {
    allFiles: sharedItems.filter((item) => item.kind !== "links").length,
    links: sharedItems.filter((item) => item.kind === "links").length,
    documents: sharedItems.filter((item) => item.kind === "documents").length,
    photos: sharedItems.filter((item) => item.kind === "photos").length,
    movies: 0,
    other: 0
  };
  const fileStats = [
    { key: "allFiles", label: "All files", value: counts.allFiles, icon: Folder },
    { key: "links", label: "All links", value: counts.links, icon: Link2 }
  ];
  const fileTypes = [
    { key: "documents", label: "Documents", detail: `${counts.documents} shared`, icon: FileText, bg: "bg-[#e5e8ff]", color: "text-[#6670d8]" },
    { key: "photos", label: "Photos", detail: `${counts.photos} shared`, icon: ImageIcon, bg: "bg-[#f6edcf]", color: "text-[#c4a14a]" },
    { key: "movies", label: "Movies", detail: "0 shared", icon: Film, bg: "bg-[#eaf7fd]", color: "text-[var(--candidate-primary)]" },
    { key: "other", label: "Other", detail: "0 shared", icon: Folder, bg: "bg-[#f8ddd7]", color: "text-[#d27662]" }
  ];
  const visibleItems = sharedItems.filter((item) => {
    if (filter === "allFiles") return item.kind !== "links";
    return item.kind === filter;
  });

  return (
    <aside className="hidden h-full min-h-0 min-w-0 overflow-y-auto bg-white xl:block">
      <div className="flex items-center gap-3 border-b border-[#e7ebf1] px-5 py-4">
        <button type="button" onClick={onCollapse} className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#f3f6f8] text-[#9aa7b5]" aria-label="Collapse shared files">
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
        <h2 className="text-base font-extrabold text-[#18212d]">Shared files</h2>
      </div>

      <div className="px-5 py-6">
        <div className="grid justify-items-center">
          <ChatAvatar title={activeChannel?.title || "Chat"} image={activeChannel?.avatar} className="h-20 w-20" />
          <p className="mt-4 max-w-[13rem] truncate text-center text-lg font-extrabold text-[#18212d]">{activeChannel?.title || "No room selected"}</p>
          <p className="mt-1 text-xs font-semibold text-[#9aa7b5]">{memberCount} members</p>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          {fileStats.map((stat) => (
            <button
              key={stat.key}
              type="button"
              onClick={() => onFilterChange(stat.key)}
              className={cx("rounded-xl p-4 text-left transition hover:bg-[#eaf7fd]", filter === stat.key ? "bg-[#eaf7fd]" : "bg-[#f6f8fa]")}
            >
              <stat.icon className={cx("h-5 w-5", filter === stat.key ? "text-[var(--candidate-primary)]" : "text-[#b5bec9]")} aria-hidden="true" />
              <p className="mt-2 text-2xl font-extrabold text-[#18212d]">{stat.value}</p>
              <p className="text-xs font-bold text-[#8d98a6]">{stat.label}</p>
            </button>
          ))}
        </div>

        <div className="mt-6 flex items-center justify-between">
          <p className="text-sm font-bold text-[#7d8a98]">File type</p>
          <button type="button" onClick={() => onNotice("Shared file list refreshed.")} className="text-[#9aa7b5]" aria-label="File type actions">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="mt-3 grid gap-2">
          {fileTypes.map((type) => (
            <button
              key={type.key}
              type="button"
              onClick={() => onFilterChange(type.key)}
              className={cx(
                "grid grid-cols-[2.3rem_minmax(0,1fr)_auto] items-center gap-3 rounded-xl px-2 py-3 text-left transition hover:bg-[#f6f8fa] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#bde9fb]",
                filter === type.key && "bg-[#f6f8fa]"
              )}
            >
              <span className={cx("flex h-9 w-9 items-center justify-center rounded-lg", type.bg, type.color)}>
                <type.icon className="h-4 w-4" aria-hidden="true" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-extrabold text-[#18212d]">{type.label}</span>
                <span className="block truncate text-[0.68rem] font-semibold text-[#9aa7b5]">{type.detail}</span>
              </span>
              <ChevronRight className="h-4 w-4 text-[#b5bec9]" aria-hidden="true" />
            </button>
          ))}
        </div>

        <div className="mt-5 border-t border-[#eef2f5] pt-4">
          <p className="text-sm font-bold text-[#7d8a98]">Selected</p>
          <div className="mt-2 grid max-h-44 gap-2 overflow-y-auto pr-1">
            {visibleItems.length === 0 ? (
              <div className="rounded-xl bg-[#f6f8fa] px-3 py-4 text-sm font-semibold text-[#8d98a6]">
                Nothing shared in this filter yet.
              </div>
            ) : (
              visibleItems.map((item) => (
                <a
                  key={item.id}
                  href={item.href}
                  target="_blank"
                  rel="noreferrer"
                  className="grid grid-cols-[2rem_minmax(0,1fr)] items-center gap-2 rounded-xl px-2 py-2 text-left transition hover:bg-[#f6f8fa]"
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#eaf7fd] text-[var(--candidate-primary)]">
                    {item.kind === "photos" ? <ImageIcon className="h-4 w-4" aria-hidden="true" /> : <Link2 className="h-4 w-4" aria-hidden="true" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-extrabold text-[#18212d]">{item.title}</span>
                    <span className="block truncate text-[0.68rem] font-semibold text-[#9aa7b5]">{item.detail}</span>
                  </span>
                </a>
              ))
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

function NewChatDialog({
  open,
  directChannels,
  selectedMemberIds,
  onToggleMember,
  groupName,
  setGroupName,
  errors,
  creating,
  onCreateGroup,
  onSelectDirect,
  onClose
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-[#071827]/35 px-4 py-6" role="dialog" aria-modal="true" aria-label="Start chat">
      <div className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#e7ebf1] px-5 py-4">
          <div>
            <p className="text-base font-extrabold text-[#18212d]">Start a chat</p>
            <p className="text-xs font-semibold text-[#8d98a6]">Choose a direct room or create a group.</p>
          </div>
          <button type="button" onClick={onClose} className="flex h-9 w-9 items-center justify-center rounded-lg text-[#8d98a6] hover:bg-[#f3f6f8]" aria-label="Close">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="grid gap-5 px-5 py-5">
          <div>
            <p className="mb-2 text-sm font-extrabold text-[#18212d]">Direct messages</p>
            <div className="grid max-h-40 gap-1 overflow-y-auto rounded-xl border border-[#e7ebf1] p-1">
              {directChannels.length === 0 ? (
                <p className="px-3 py-4 text-sm font-semibold text-[#8d98a6]">No direct users are available yet.</p>
              ) : (
                directChannels.map((channel) => (
                  <button
                    key={channel.id}
                    type="button"
                    onClick={() => onSelectDirect(channel)}
                    className="grid grid-cols-[2.25rem_minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-[#f3f6f8]"
                  >
                    <ChatAvatar title={channel.title} image={channel.avatar} className="h-9 w-9" />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-extrabold text-[#18212d]">{channel.title}</span>
                      <span className="block truncate text-xs font-semibold text-[#8d98a6]">{channel.subtitle}</span>
                    </span>
                    <ChevronRight className="h-4 w-4 text-[#b5bec9]" aria-hidden="true" />
                  </button>
                ))
              )}
            </div>
          </div>

          <div>
            <p className="mb-2 text-sm font-extrabold text-[#18212d]">Create group</p>
            <input
              value={groupName}
              onChange={(event) => setGroupName(event.target.value)}
              placeholder="Group name"
              maxLength={80}
              aria-invalid={Boolean(fieldError(errors, "name")) || undefined}
              className="h-11 w-full rounded-xl border border-[#dfe7ee] px-3 text-sm font-semibold text-[#18212d] outline-none focus:ring-4 focus:ring-[#bde9fb]"
            />
            {fieldError(errors, "name") && <p className="mt-1 text-xs font-bold text-rose-600">{fieldError(errors, "name")}</p>}
            <div className="mt-3 grid max-h-36 gap-1 overflow-y-auto rounded-xl border border-[#e7ebf1] p-1">
              {directChannels.map((channel) => (
                <label key={channel.id} className="grid cursor-pointer grid-cols-[2.25rem_minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-3 py-2 hover:bg-[#f3f6f8]">
                  <ChatAvatar title={channel.title} image={channel.avatar} className="h-9 w-9" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-extrabold text-[#18212d]">{channel.title}</span>
                    <span className="block truncate text-xs font-semibold text-[#8d98a6]">{channel.subtitle}</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={selectedMemberIds.includes(channel.id)}
                    onChange={() => onToggleMember(channel.id)}
                    className="h-4 w-4 accent-[var(--candidate-primary)]"
                  />
                </label>
              ))}
            </div>
            {fieldError(errors, "memberIds") && <p className="mt-2 text-xs font-bold text-rose-600">{fieldError(errors, "memberIds")}</p>}
            <button
              type="button"
              onClick={onCreateGroup}
              disabled={creating || !groupName.trim() || selectedMemberIds.length === 0}
              className="mt-3 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-xl bg-[var(--candidate-primary)] px-4 text-sm font-extrabold text-white transition hover:bg-[var(--candidate-primary-hover)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {creating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <UserPlus className="h-4 w-4" aria-hidden="true" />}
              Create group
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Chat() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [channels, setChannels] = useState([]);
  const [activeChannel, setActiveChannel] = useState(null);
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("available");
  const [channelFilter, setChannelFilter] = useState("all");
  const [activeTab, setActiveTab] = useState("messages");
  const [sharedFilter, setSharedFilter] = useState("allFiles");
  const [isSharedOpen, setIsSharedOpen] = useState(true);
  const [isStatusOpen, setIsStatusOpen] = useState(false);
  const [isChannelActionsOpen, setIsChannelActionsOpen] = useState(false);
  const [isEmojiOpen, setIsEmojiOpen] = useState(false);
  const [isNewChatOpen, setIsNewChatOpen] = useState(false);
  const [selectedMemberIds, setSelectedMemberIds] = useState([]);
  const [groupName, setGroupName] = useState("");
  const [attachedFiles, setAttachedFiles] = useState([]);
  const [composerError, setComposerError] = useState("");
  const [groupErrors, setGroupErrors] = useState({});
  const [notice, setNotice] = useState("");
  const [isLoadingChannels, setIsLoadingChannels] = useState(true);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isCreatingGroup, setIsCreatingGroup] = useState(false);
  const [error, setError] = useState("");
  const [chatUser, setChatUser] = useState(null);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const noticeTimeoutRef = useRef(null);
  const activeChannelRef = useRef(null);
  const loadChannelsRef = useRef(null);
  const socketRef = useRef(null);

  const directChannels = useMemo(() => channels.filter((channel) => channel.type === "direct"), [channels]);

  const showNotice = useCallback((message) => {
    setNotice(message);
    window.clearTimeout(noticeTimeoutRef.current);
    noticeTimeoutRef.current = window.setTimeout(() => setNotice(""), 2400);
  }, []);

  const loadChannels = useCallback(async ({ keepActive = true } = {}) => {
    if (!user) return [];

    setIsLoadingChannels(true);
    setError("");
    try {
      const [usersResponse, groupsResponse] = await Promise.all([getChatUsers(user), getChatGroups(user)]);
      const nextChannels = buildChannels(
        usersResponse.data.users || [],
        groupsResponse.data.groups || [],
        usersResponse.data.unSeenMessages || {}
      );
      setChannels(nextChannels);
      setActiveChannel((current) => {
        if (keepActive && current) {
          return nextChannels.find((channel) => channel.id === current.id && channel.type === current.type) || nextChannels[0] || null;
        }
        return nextChannels[0] || null;
      });
      return nextChannels;
    } catch (err) {
      setError(getChatErrorMessage(err));
      return [];
    } finally {
      setIsLoadingChannels(false);
    }
  }, [user]);

  useEffect(() => {
    loadChannelsRef.current = loadChannels;
  }, [loadChannels]);

  useEffect(() => {
    activeChannelRef.current = activeChannel;
  }, [activeChannel]);

  useEffect(() => {
    let cancelled = false;

    async function syncChatUser() {
      if (!user) {
        setChatUser(null);
        return;
      }

      try {
        const response = await getCurrentChatUser(user);
        if (!cancelled) setChatUser(response.data.userData || null);
      } catch (err) {
        if (!cancelled) setError(getChatErrorMessage(err));
      }
    }

    syncChatUser();
    return () => {
      cancelled = true;
    };
  }, [user]);

  useEffect(() => {
    if (!user || !chatUser?._id) return undefined;

    const socket = createChatSocket(user, chatUser);
    socketRef.current = socket;

    const refreshChannels = () => {
      loadChannelsRef.current?.({ keepActive: true });
    };

    const handleNewMessage = (message) => {
      const currentChannel = activeChannelRef.current;
      if (messageBelongsToChannel(message, currentChannel)) {
        setMessages((current) => appendUniqueMessage(current, message));
      }
      refreshChannels();
    };

    const handleNewGroupMessage = (payload) => {
      const message = payload?.message || payload;
      const currentChannel = activeChannelRef.current;
      if (currentChannel?.type === "group" && String(payload?.groupId || message?.group) === String(currentChannel.id)) {
        setMessages((current) => appendUniqueMessage(current, message));
      }
      refreshChannels();
    };

    const handleDeletedMessage = (messageIdValue) => {
      setMessages((current) => current.filter((message) => messageId(message) !== String(messageIdValue)));
      refreshChannels();
    };

    const handleEditedMessage = (updatedMessage) => {
      setMessages((current) => current.map((message) => (messageId(message) === messageId(updatedMessage) ? updatedMessage : message)));
      refreshChannels();
    };

    const handleGroupDeletedMessage = (payload) => handleDeletedMessage(payload?.messageId || payload);
    const handleGroupEditedMessage = (payload) => handleEditedMessage(payload?.message || payload);

    socket.on("newMessage", handleNewMessage);
    socket.on("message:new", handleNewMessage);
    socket.on("newGroupMessage", handleNewGroupMessage);
    socket.on("messageDeleted", handleDeletedMessage);
    socket.on("messageEdited", handleEditedMessage);
    socket.on("groupMessageDeleted", handleGroupDeletedMessage);
    socket.on("groupMessageEdited", handleGroupEditedMessage);

    return () => {
      socket.off("newMessage", handleNewMessage);
      socket.off("message:new", handleNewMessage);
      socket.off("newGroupMessage", handleNewGroupMessage);
      socket.off("messageDeleted", handleDeletedMessage);
      socket.off("messageEdited", handleEditedMessage);
      socket.off("groupMessageDeleted", handleGroupDeletedMessage);
      socket.off("groupMessageEdited", handleGroupEditedMessage);
      socket.disconnect();
      if (socketRef.current === socket) socketRef.current = null;
    };
  }, [chatUser, user]);

  useEffect(() => {
    loadChannels({ keepActive: false });
  }, [loadChannels]);

  useEffect(() => {
    let cancelled = false;

    async function loadMessages() {
      if (!activeChannel) {
        setMessages([]);
        return;
      }

      setIsLoadingMessages(true);
      setError("");
      try {
        const response =
          activeChannel.type === "group"
            ? await getGroupMessages(activeChannel.id, user)
            : await getDirectMessages(activeChannel.id, user);
        if (!cancelled) setMessages(response.data.messages || []);
      } catch (err) {
        if (!cancelled) setError(getChatErrorMessage(err));
      } finally {
        if (!cancelled) setIsLoadingMessages(false);
      }
    }

    loadMessages();
    return () => {
      cancelled = true;
    };
  }, [activeChannel, user]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, activeChannel]);

  useEffect(() => {
    setActiveTab("messages");
    setSharedFilter("allFiles");
    setIsEmojiOpen(false);
    setAttachedFiles([]);
    setComposerError("");
  }, [activeChannel]);

  useEffect(() => {
    return () => window.clearTimeout(noticeTimeoutRef.current);
  }, []);

  const filteredChannels = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return channels.filter((channel) => {
      const matchesFilter = channelFilter === "all" || channel.type === channelFilter;
      const matchesQuery = !normalizedQuery || normalizeChannelText(channel).includes(normalizedQuery);
      return matchesFilter && matchesQuery;
    });
  }, [channels, channelFilter, query]);

  function handleStatusChange(nextStatus) {
    setStatus(nextStatus);
    setIsStatusOpen(false);
    showNotice(`Status changed to ${nextStatus}.`);
  }

  function handleToggleMember(memberId) {
    setGroupErrors((current) => clearFieldError(current, "memberIds"));
    setSelectedMemberIds((current) =>
      current.includes(memberId) ? current.filter((id) => id !== memberId) : [...current, memberId]
    );
  }

  async function handleCreateGroup() {
    if (isCreatingGroup) return;
    const validation = validateForm(chatGroupSchema, { name: groupName, memberIds: selectedMemberIds });
    if (!validation.data) {
      setGroupErrors(validation.errors);
      setError(validation.formError);
      return;
    }

    setIsCreatingGroup(true);
    setError("");
    setGroupErrors({});
    try {
      const response = await createChatGroup(validation.data, user);
      const createdGroup = response.data.group;
      const nextChannels = await loadChannels({ keepActive: true });
      const nextActive = nextChannels.find((channel) => channel.type === "group" && channel.id === createdGroup?._id);
      if (nextActive) setActiveChannel(nextActive);
      setGroupName("");
      setSelectedMemberIds([]);
      setIsNewChatOpen(false);
      showNotice("Group chat created.");
    } catch (err) {
      setError(getChatErrorMessage(err));
    } finally {
      setIsCreatingGroup(false);
    }
  }

  async function handleAttachFile(event) {
    const files = [...(event.target.files || [])];
    event.target.value = "";
    if (files.length === 0) return;
    if (attachedFiles.length >= CHAT_MAX_ATTACHMENTS) {
      showNotice(`Attach up to ${CHAT_MAX_ATTACHMENTS} files at once.`);
      return;
    }
    const room = CHAT_MAX_ATTACHMENTS - attachedFiles.length;
    const selectedFiles = files.slice(0, room);
    const attachments = [];

    for (const file of selectedFiles) {
      const fileError = validateChatFile(file);
      if (fileError) {
        showNotice(fileError);
        continue;
      }
      try {
        const dataUrl = await readFileAsDataUrl(file);
        attachments.push({
          id: createClientMessageId(),
          name: file.name,
          type: file.type || "application/octet-stream",
          size: file.size,
          dataUrl: String(dataUrl)
        });
      } catch {
        showNotice(`Could not read ${file.name}.`);
      }
    }

    if (attachments.length > 0) {
      setAttachedFiles((current) => [...current, ...attachments]);
      setComposerError("");
      showNotice(attachments.length === 1 ? "File attached." : `${attachments.length} files attached.`);
    }
    if (files.length > selectedFiles.length) {
      showNotice(`Only ${room} more attachment${room === 1 ? "" : "s"} can be added.`);
    }
  }

  function handleSelectDirect(channel) {
    setActiveChannel(channel);
    setIsNewChatOpen(false);
    setQuery("");
  }

  function buildOptimisticMessage(payload, status = "sending", errorMessage = "") {
    const createdAt = new Date().toISOString();
    const optimisticAttachments = payload.attachments.map((attachment) => ({
      name: attachment.name,
      contentType: attachment.type,
      size: attachment.size,
      url: attachment.dataUrl,
      dataUrl: attachment.dataUrl
    }));
    const imageAttachment = optimisticAttachments.find((attachment) => attachment.contentType?.startsWith("image/"));
    const sender = {
      _id: chatUser?._id || `fastapi:${user?.id || ""}`,
      appUserId: chatUser?.appUserId || `fastapi:${user?.id || ""}`,
      email: chatUser?.email || user?.email || "",
      username: getUserDisplayName(chatUser || user),
      displayName: getUserDisplayName(chatUser || user),
      profilePicture: chatUser?.profilePicture
    };

    return {
      _id: payload.clientMessageId,
      clientMessageId: payload.clientMessageId,
      sender,
      receiver: activeChannel.type === "direct" ? activeChannel.id : undefined,
      group: activeChannel.type === "group" ? activeChannel.id : undefined,
      text: payload.text,
      image: imageAttachment?.url || "",
      attachments: optimisticAttachments,
      createdAt,
      timestamp: createdAt,
      __status: status,
      __error: errorMessage,
      __retryPayload: payload
    };
  }

  async function sendPreparedMessage(payload, { appendOptimistic = true } = {}) {
    if (!activeChannel) return;
    if (appendOptimistic) {
      setMessages((current) => appendUniqueMessage(current, buildOptimisticMessage(payload)));
    }

    setIsSending(true);
    setError("");
    try {
      const response =
        activeChannel.type === "group"
          ? await sendGroupMessage(activeChannel.id, payload, user)
          : await sendDirectMessage(activeChannel.id, payload, user);
      setMessages((current) => appendUniqueMessage(current, response.data.message));
      setIsEmojiOpen(false);
    } catch (err) {
      const message = getChatErrorMessage(err);
      setMessages((current) =>
        current.map((item) =>
          item.clientMessageId === payload.clientMessageId
            ? buildOptimisticMessage(payload, "failed", message)
            : item
        )
      );
      setError(message);
    } finally {
      setIsSending(false);
    }
  }

  async function handleSendMessage(event) {
    event.preventDefault();
    if (!activeChannel || isSending) return;

    const validation = validateForm(chatMessageSchema, { text: draft, attachments: attachedFiles });
    if (!validation.data) {
      setComposerError(validation.formError);
      return;
    }

    const payload = {
      text: validation.data.text,
      attachments: validation.data.attachments,
      clientMessageId: createClientMessageId()
    };
    setDraft("");
    setAttachedFiles([]);
    setComposerError("");
    await sendPreparedMessage(payload);
  }

  async function handleRetryMessage(message) {
    if (!message.__retryPayload || isSending) return;
    setMessages((current) =>
      current.map((item) =>
        isSameMessage(item, message)
          ? { ...item, __status: "sending", __error: "" }
          : item
      )
    );
    await sendPreparedMessage(message.__retryPayload, { appendOptimistic: false });
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--candidate-surface-soft)]" data-chat-shell>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.zip"
        multiple
        className="hidden"
        onChange={handleAttachFile}
      />
      {notice && (
        <div className="fixed right-4 top-4 z-50 rounded-xl border border-[#bde9fb] bg-white px-4 py-3 text-sm font-extrabold text-[#18212d] shadow-xl">
          {notice}
        </div>
      )}
      {error && (
        <div className="px-3 pt-3">
          <Alert>
            <span className="inline-flex items-center gap-2">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {error}
            </span>
          </Alert>
        </div>
      )}

      <section
        className={cx(
          "grid min-h-0 flex-1 overflow-hidden bg-white lg:grid-cols-[18rem_minmax(0,1fr)]",
          isSharedOpen && "xl:grid-cols-[18rem_minmax(0,1fr)_18rem]"
        )}
      >
        <ConversationPanel
          user={user}
          query={query}
          setQuery={setQuery}
          channels={filteredChannels}
          activeChannel={activeChannel}
          onSelect={setActiveChannel}
          loading={isLoadingChannels}
          status={status}
          statusOpen={isStatusOpen}
          onToggleStatus={() => {
            setIsStatusOpen((current) => !current);
            setIsChannelActionsOpen(false);
          }}
          onStatusChange={handleStatusChange}
          onBack={() => navigate(-1)}
          onOpenNewChat={() => setIsNewChatOpen(true)}
          actionsOpen={isChannelActionsOpen}
          onToggleActions={() => {
            setIsChannelActionsOpen((current) => !current);
            setIsStatusOpen(false);
          }}
          onRefresh={() => {
            setIsChannelActionsOpen(false);
            loadChannels({ keepActive: true }).then(() => showNotice("Chats refreshed."));
          }}
          channelFilter={channelFilter}
          onChannelFilterChange={(filter) => {
            setChannelFilter(filter);
            setIsChannelActionsOpen(false);
          }}
        />
        <ChatCenter
          activeChannel={activeChannel}
          messages={messages}
          loading={isLoadingMessages}
          draft={draft}
          setDraft={(value) => {
            setDraft(value);
            setComposerError("");
          }}
          sending={isSending}
          onSend={handleSendMessage}
          user={user}
          endRef={messagesEndRef}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          emojiOpen={isEmojiOpen}
          onToggleEmoji={() => setIsEmojiOpen((current) => !current)}
          onEmojiSelect={(emoji) => {
            setDraft((current) => `${current}${emoji}`);
            setIsEmojiOpen(false);
            setComposerError("");
          }}
          onAttachClick={() => fileInputRef.current?.click()}
          attachedFiles={attachedFiles}
          onRemoveAttachment={(attachmentId) => setAttachedFiles((current) => current.filter((attachment) => attachment.id !== attachmentId))}
          composerError={composerError}
          sharedOpen={isSharedOpen}
          onToggleShared={() => setIsSharedOpen((current) => !current)}
          onOpenNewChat={() => setIsNewChatOpen(true)}
          onRetryMessage={handleRetryMessage}
        />
        {isSharedOpen && (
          <SharedFilesPanel
            activeChannel={activeChannel}
            messages={messages}
            filter={sharedFilter}
            onFilterChange={setSharedFilter}
            onCollapse={() => setIsSharedOpen(false)}
            onNotice={showNotice}
          />
        )}
      </section>
      <NewChatDialog
        open={isNewChatOpen}
        directChannels={directChannels}
        selectedMemberIds={selectedMemberIds}
        onToggleMember={handleToggleMember}
        groupName={groupName}
        setGroupName={(value) => {
          setGroupName(value);
          setGroupErrors((current) => clearFieldError(current, "name"));
        }}
        errors={groupErrors}
        creating={isCreatingGroup}
        onCreateGroup={handleCreateGroup}
        onSelectDirect={handleSelectDirect}
        onClose={() => setIsNewChatOpen(false)}
      />
    </div>
  );
}
