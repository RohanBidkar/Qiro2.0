import { useState, useEffect } from 'react';
import { useUser } from '@clerk/clerk-react';
import './Sidebar.css';

// Use relative URL in production, localhost in development
const API_URL = import.meta.env.PROD ? '' : 'http://127.0.0.1:8000';

const Sidebar = ({ isOpen, onClose, onNewChat, onSelectChat, currentChatId }) => {
    const [chats, setChats] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const { user } = useUser();

    useEffect(() => {
        if (isOpen) {
            fetchChats();
        }
    }, [isOpen]);

    const fetchChats = async () => {
        setIsLoading(true);
        try {
            // Only fetch chats if user is signed in
            if (!user) {
                setChats([]);
                setIsLoading(false);
                return;
            }

            const url = `${API_URL}/chats?user_id=${user.id}`;
            const response = await fetch(url);
            if (response.ok) {
                const data = await response.json();
                setChats(data.chats || []);
            }
        } catch (error) {
            console.error('Error fetching chats:', error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleDeleteChat = async (chatId, e) => {
        e.stopPropagation();
        try {
            if (!user) return;

            const url = `${API_URL}/chats/${chatId}?user_id=${user.id}`;
            const response = await fetch(url, {
                method: 'DELETE',
            });
            if (response.ok) {
                setChats(chats.filter(chat => chat.id !== chatId));
            }
        } catch (error) {
            console.error('Error deleting chat:', error);
        }
    };

    const CloseIcon = () => (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
    );

    const TrashIcon = () => (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
        </svg>
    );

    const PlusIcon = () => (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
        </svg>
    );

    return (
        <>
            <div className={`sidebar-overlay ${isOpen ? 'active' : ''}`} onClick={onClose}></div>
            <div className={`sidebar ${isOpen ? 'open' : ''}`}>
                <div className="sidebar-header">
                    <button className="close-btn" onClick={onClose}>
                        <CloseIcon />
                    </button>
                </div>

                <button className="new-chat-btn" onClick={() => { onNewChat(); onClose(); }}>
                    <PlusIcon />
                    <span>New chat</span>
                </button>

                <div className="sidebar-section">
                    <h3 className="section-title">RECENT CHATS</h3>

                    {isLoading ? (
                        <div className="loading-chats">Loading...</div>
                    ) : chats.length === 0 ? (
                        <div className="empty-state">
                            <p>Sign in to save your chat history</p>
                        </div>
                    ) : (
                        <div className="chat-list">
                            {chats.map((chat) => (
                                <div
                                    key={chat.id}
                                    className={`chat-item ${currentChatId === chat.id ? 'active' : ''}`}
                                    onClick={() => { onSelectChat(chat.id); onClose(); }}
                                >
                                    <div className="chat-info">
                                        <div className="chat-title">{chat.title || 'New Chat'}</div>
                                        <div className="chat-date">{new Date(chat.created_at).toLocaleDateString()}</div>
                                    </div>
                                    <button
                                        className="delete-chat-btn"
                                        onClick={(e) => handleDeleteChat(chat.id, e)}
                                    >
                                        <TrashIcon />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                <div className="sidebar-footer">
                    <button className="settings-btn">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="3"></circle>
                            <path d="M12 1v6m0 6v6m5.196-15.196l-4.242 4.242m0 5.908l-4.242 4.242M23 12h-6m-6 0H1m15.196 5.196l-4.242-4.242m0-5.908l-4.242-4.242"></path>
                        </svg>
                        <span>Settings</span>
                    </button>
                </div>
            </div>
        </>
    );
};

export default Sidebar;
