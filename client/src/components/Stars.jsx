import { useEffect, useRef } from 'react';
import './Stars.css';

const Stars = ({ count = 100 }) => {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        let animationFrameId;
        let stars = [];

        // Set canvas size
        const resizeCanvas = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            initStars();
        };

        // Initialize stars
        const initStars = () => {
            stars = [];
            for (let i = 0; i < count; i++) {
                stars.push({
                    x: Math.random() * canvas.width,
                    y: Math.random() * canvas.height,
                    radius: Math.random() * 1.5 + 0.5,
                    opacity: Math.random(),
                    fadeSpeed: Math.random() * 0.02 + 0.01,
                    fadeDirection: Math.random() > 0.5 ? 1 : -1,
                    color: getStarColor()
                });
            }
        };

        // Get random star color (cyan, blue, teal palette)
        const getStarColor = () => {
            const colors = [
                'rgba(94, 234, 212', // Teal
                'rgba(59, 130, 246', // Blue
                'rgba(6, 182, 212',  // Cyan
                'rgba(167, 243, 208', // Light teal
                'rgba(255, 255, 255'  // White
            ];
            return colors[Math.floor(Math.random() * colors.length)];
        };

        // Animation loop
        const animate = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            stars.forEach(star => {
                // Update opacity for blinking effect
                star.opacity += star.fadeSpeed * star.fadeDirection;

                // Reverse fade direction at boundaries
                if (star.opacity >= 1) {
                    star.opacity = 1;
                    star.fadeDirection = -1;
                } else if (star.opacity <= 0.1) {
                    star.opacity = 0.1;
                    star.fadeDirection = 1;
                }

                // Draw star
                ctx.beginPath();
                ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
                ctx.fillStyle = `${star.color}, ${star.opacity})`;
                ctx.fill();

                // Add glow effect for larger stars
                if (star.radius > 1) {
                    ctx.shadowBlur = 10;
                    ctx.shadowColor = `${star.color}, ${star.opacity * 0.5})`;
                } else {
                    ctx.shadowBlur = 0;
                }
            });

            animationFrameId = requestAnimationFrame(animate);
        };

        // Initialize and start animation
        resizeCanvas();
        animate();

        // Handle window resize
        window.addEventListener('resize', resizeCanvas);

        // Cleanup
        return () => {
            window.removeEventListener('resize', resizeCanvas);
            cancelAnimationFrame(animationFrameId);
        };
    }, [count]);

    return <canvas ref={canvasRef} className="stars-canvas" />;
};

export default Stars;
