import React from 'react';

const MenuButton = ({ onClick }) => {
    const buttonStyle = {
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '5px',
        position: 'relative',
        zIndex: 10,
        borderRadius: '0.375rem',
        padding: '8px',
        cursor: 'pointer',
        border: '1px solid rgba(255, 255, 255, 0.3)',
        outline: 'none',
        backgroundColor: 'transparent',
        transition: 'all 0.3s ease'
    };

    const barStyle = {
        width: '24px',
        height: '2px',
        backgroundColor: 'white',
        borderRadius: '9999px',
        transition: 'all 0.3s ease'
    };

    return (
        <button
            onClick={onClick}
            style={buttonStyle}
            aria-label="Toggle sidebar"
            onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
                const bars = e.currentTarget.querySelectorAll('span');
                bars.forEach(bar => bar.style.backgroundColor = '#22d3ee');
            }}
            onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent';
                const bars = e.currentTarget.querySelectorAll('span');
                bars.forEach(bar => bar.style.backgroundColor = 'white');
            }}
        >
            <span style={barStyle}></span>
            <span style={barStyle}></span>
            <span style={barStyle}></span>
        </button>
    );
}

export default MenuButton;
