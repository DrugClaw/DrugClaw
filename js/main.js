/**
 * Qclaw Landing Template - JavaScript
 * 
 * 功能：
 * - 自定义光标跟随 (PC)
 * - 粒子背景
 * - 导航栏滚动效果
 * - 滚动触发动画
 * - 评价无限滚动
 */

document.addEventListener('DOMContentLoaded', () => {
  
  // ===== 自定义光标 (PC only) =====
  const cursorDot = document.getElementById('cursorDot');
  const cursorRing = document.getElementById('cursorRing');
  const cursorGlow = document.getElementById('cursorGlow');
  
  if (cursorDot && cursorRing && cursorGlow) {
    let mouseX = 0, mouseY = 0;
    let ringX = 0, ringY = 0;
    
    document.addEventListener('mousemove', (e) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
      
      // 光点直接跟随
      cursorDot.style.left = mouseX + 'px';
      cursorDot.style.top = mouseY + 'px';
      
      // 光晕跟随
      cursorGlow.style.left = mouseX + 'px';
      cursorGlow.style.top = mouseY + 'px';
    });
    
    // 圆环平滑跟随
    function animateRing() {
      ringX += (mouseX - ringX) * 0.15;
      ringY += (mouseY - ringY) * 0.15;
      
      cursorRing.style.left = ringX + 'px';
      cursorRing.style.top = ringY + 'px';
      
      requestAnimationFrame(animateRing);
    }
    animateRing();
    
    // 悬停效果
    const hoverElements = document.querySelectorAll('a, button, .btn-download, .feature-card, .demo-card, .testimonial-card, .step-item');
    
    hoverElements.forEach(el => {
      el.addEventListener('mouseenter', () => {
        cursorRing.classList.add('hovering');
      });
      
      el.addEventListener('mouseleave', () => {
        cursorRing.classList.remove('hovering');
      });
    });
  }
  
  // ===== 粒子背景 =====
  const canvas = document.getElementById('particles-canvas');
  if (canvas) {
    const ctx = canvas.getContext('2d');
    let particles = [];
    const particleCount = 80;
    
    function resizeCanvas() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    
    class Particle {
      constructor() {
        this.reset();
      }
      
      reset() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.vx = (Math.random() - 0.5) * 0.3;
        this.vy = (Math.random() - 0.5) * 0.3;
        this.radius = Math.random() * 1.5 + 0.5;
        this.opacity = Math.random() * 0.3 + 0.1;
      }
      
      update() {
        this.x += this.vx;
        this.y += this.vy;
        
        if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
        if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
      }
      
      draw() {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(33, 197, 106, ${this.opacity})`;
        ctx.fill();
      }
    }
    
    // 初始化粒子
    for (let i = 0; i < particleCount; i++) {
      particles.push(new Particle());
    }
    
    // 绘制连线
    function drawLines() {
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          
          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(33, 197, 106, ${0.05 * (1 - dist / 120)})`;
            ctx.stroke();
          }
        }
      }
    }
    
    function animate() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      particles.forEach(p => {
        p.update();
        p.draw();
      });
      
      drawLines();
      
      requestAnimationFrame(animate);
    }
    
    animate();
  }
  
  // ===== 导航栏滚动效果 =====
  const navbar = document.getElementById('navbar');
  if (navbar) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 50) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.remove('scrolled');
      }
    });
  }
  
  // ===== 滚动触发动画 =====
  const revealElements = document.querySelectorAll('.reveal');
  
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
      }
    });
  }, {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
  });
  
  revealElements.forEach(el => {
    revealObserver.observe(el);
  });
  
  // ===== 评价无限滚动 =====
  const track = document.getElementById('testimonialsTrack');
  if (track) {
    // 复制所有卡片
    const cards = track.querySelectorAll('.testimonial-card');
    cards.forEach(card => {
      const clone = card.cloneNode(true);
      track.appendChild(clone);
    });
  }
  
  // ===== 平滑滚动 =====
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        target.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });
  
  // ===== 打字机效果 (可选) =====
  function typeWriter(element, text, speed = 50) {
    let i = 0;
    element.textContent = '';
    
    function type() {
      if (i < text.length) {
        element.textContent += text.charAt(i);
        i++;
        setTimeout(type, speed);
      }
    }
    
    type();
  }
  
  // ===== 统计数字动画 (可选) =====
  function animateCounter(element, target, duration = 2000) {
    const start = 0;
    const increment = target / (duration / 16);
    let current = start;
    
    function update() {
      current += increment;
      if (current < target) {
        element.textContent = Math.floor(current);
        requestAnimationFrame(update);
      } else {
        element.textContent = target;
      }
    }
    
    update();
  }
  
  console.log('🦞 Qclaw Landing Template loaded');
});
