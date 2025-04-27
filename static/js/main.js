// Main JavaScript for Antlers Parallax Website

// Wait for DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize parallax effects
    initParallax();
    
    // Initialize navigation
    initNavigation();
    
    // Initialize animations
    initAnimations();
    
    // Initialize any forms
    initForms();
    
    // Initialize category filters
    initCategoryFilters();
});

/**
 * Initialize parallax scrolling effects
 */
function initParallax() {
    // Check if device supports parallax (avoid on mobile for performance)
    const supportsParallax = window.innerWidth > 768;
    
    if (supportsParallax) {
        // Enhanced parallax scroll effect
        window.addEventListener('scroll', function() {
            const scrolled = window.pageYOffset;
            
            // Apply more dramatic parallax effect to elements with .parallax-bg class
            const parallaxElements = document.querySelectorAll('.parallax-bg');
            parallaxElements.forEach(el => {
                const speed = parseFloat(el.getAttribute('data-speed') || 0.5);
                el.style.transform = `translate3d(0, ${scrolled * speed}px, 0)`;
                el.style.transition = 'transform 0.1s ease-out'; // Smoother transition
            });
            
            // Enhance hero section parallax effect
            const heroSection = document.querySelector('.hero-section');
            if (heroSection) {
                heroSection.style.backgroundPositionY = `calc(50% + ${scrolled * 0.5}px)`;
            }
            
            // Apply parallax effect to section titles for added depth
            const sectionTitles = document.querySelectorAll('.section-title');
            sectionTitles.forEach(title => {
                const rect = title.getBoundingClientRect();
                const centerOffset = window.innerHeight / 2 - rect.top - rect.height / 2;
                if (Math.abs(centerOffset) < window.innerHeight) {
                    title.style.transform = `translateY(${centerOffset * 0.05}px)`;
                }
            });
            
            // Add parallax to cards for depth effect
            const cards = document.querySelectorAll('.card');
            cards.forEach(card => {
                const rect = card.getBoundingClientRect();
                const centerOffset = window.innerHeight / 2 - rect.top - rect.height / 2;
                if (Math.abs(centerOffset) < window.innerHeight) {
                    card.style.transform = `translateY(${centerOffset * 0.02}px)`;
                }
            });
        });
        
        // Add scroll trigger for content elements
        const contentWrappers = document.querySelectorAll('.content-wrapper');
        contentWrappers.forEach(wrapper => {
            wrapper.setAttribute('data-depth', Math.random() * 0.2 + 0.1);
            updateElementOnScroll(wrapper);
        });
        
        // Initial call to position elements
        triggerScrollUpdate();
    } else {
        // For mobile, add simple fade effects instead of parallax
        document.querySelectorAll('.parallax-section').forEach(section => {
            section.style.backgroundAttachment = 'scroll';
        });
    }
}

/**
 * Update element based on scroll position
 */
function updateElementOnScroll(element) {
    const depth = parseFloat(element.getAttribute('data-depth') || 0.1);
    window.addEventListener('scroll', function() {
        const scrollTop = window.pageYOffset;
        const elementTop = element.offsetTop;
        const scrollDistance = scrollTop - elementTop;
        
        if (Math.abs(scrollDistance) < window.innerHeight * 1.5) {
            const translateY = scrollDistance * depth;
            element.style.transform = `translateY(${translateY}px)`;
        }
    });
}

/**
 * Trigger a scroll update
 */
function triggerScrollUpdate() {
    // Manually trigger scroll event to position elements initially
    window.dispatchEvent(new Event('scroll'));
}

/**
 * Initialize navigation effects
 */
function initNavigation() {
    const navbar = document.querySelector('.navbar');
    
    // Add scrolled class to navbar when scrolling down
    if (navbar) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 50) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        });
    }
    
    // Smooth scroll for anchor links
    const anchorLinks = document.querySelectorAll('a[href^="#"]');
    anchorLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;
            
            e.preventDefault();
            const targetElement = document.querySelector(targetId);
            
            if (targetElement) {
                window.scrollTo({
                    top: targetElement.offsetTop - 80,
                    behavior: 'smooth'
                });
            }
        });
    });
}

/**
 * Initialize animations for UI elements
 */
function initAnimations() {
    // Animate elements when they come into view
    const animatedElements = document.querySelectorAll('.fade-in');
    
    // Observer for animation triggers
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = 1;
                entry.target.style.transform = 'translateY(0)';
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });
    
    // Apply initial styles and observe elements
    animatedElements.forEach(el => {
        el.style.opacity = 0;
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
        observer.observe(el);
    });
    
    // Card hover effects
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-8px)';
            this.style.boxShadow = '0 10px 20px rgba(0,0,0,0.15)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
        });
    });
}

/**
 * Initialize form validations and behaviors
 */
function initForms() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let isValid = true;
            
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    isValid = false;
                    field.classList.add('is-invalid');
                } else {
                    field.classList.remove('is-invalid');
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                // Show validation message
                const firstInvalid = form.querySelector('.is-invalid');
                if (firstInvalid) {
                    firstInvalid.focus();
                }
            }
        });
    });
}

/**
 * Utility function to show flash messages
 * @param {string} message - The message to display
 * @param {string} type - The type of message (success, error, info)
 */
function showFlashMessage(message, type = 'info') {
    const flashContainer = document.querySelector('.flash-container') || createFlashContainer();
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type === 'error' ? 'danger' : type}`;
    alertDiv.innerHTML = message;
    
    // Add close button
    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'close';
    closeButton.setAttribute('aria-label', 'Close');
    closeButton.innerHTML = '<span aria-hidden="true">&times;</span>';
    closeButton.addEventListener('click', function() {
        alertDiv.remove();
    });
    
    alertDiv.appendChild(closeButton);
    flashContainer.appendChild(alertDiv);
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        alertDiv.classList.add('fade-out');
        setTimeout(() => alertDiv.remove(), 500);
    }, 5000);
}

/**
 * Creates a container for flash messages if not already present
 */
function createFlashContainer() {
    const flashContainer = document.createElement('div');
    flashContainer.className = 'flash-container';
    flashContainer.style.position = 'fixed';
    flashContainer.style.top = '20px';
    flashContainer.style.right = '20px';
    flashContainer.style.zIndex = '9999';
    flashContainer.style.maxWidth = '350px';
    document.body.appendChild(flashContainer);
    return flashContainer;
}

/**
 * Initialize image previews for file upload fields
 */
function initImagePreviews() {
    const imageInputs = document.querySelectorAll('input[type="file"][accept*="image"]');
    
    imageInputs.forEach(input => {
        input.addEventListener('change', function(e) {
            const previewId = this.getAttribute('data-preview');
            const previewElement = document.getElementById(previewId);
            
            if (previewElement && this.files && this.files[0]) {
                const reader = new FileReader();
                
                reader.onload = function(e) {
                    previewElement.src = e.target.result;
                    previewElement.style.display = 'block';
                };
                
                reader.readAsDataURL(this.files[0]);
            }
        });
    });
}

// Call image preview initialization
initImagePreviews();

/**
 * Initialize category filter buttons
 */
function initCategoryFilters() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    const itemElements = document.querySelectorAll('[data-category]');
    
    // Skip if no filter buttons found
    if (filterButtons.length === 0) return;
    
    filterButtons.forEach(button => {
        button.addEventListener('click', function() {
            const category = this.getAttribute('data-category');
            
            // Update active state on buttons
            filterButtons.forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Add active state to clicked button
            this.classList.add('active');
            
            // Filter items AND highlight matching ones
            itemElements.forEach(item => {
                // Only target the item cards, not the buttons
                if (item.classList.contains('fade-in')) {
                    const itemCategory = item.getAttribute('data-category').toLowerCase();
                    
                    if (category === 'all') {
                        // Show all items
                        item.style.display = 'block';
                        // Reset to normal state
                        item.style.transform = 'scale(1)';
                        item.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)';
                        item.style.opacity = '1';
                        item.style.zIndex = '0';
                    } else if (itemCategory === category) {
                        // Show and highlight matching items
                        item.style.display = 'block';
                        item.style.transform = 'scale(1.03)';
                        item.style.boxShadow = '0 15px 30px rgba(0, 0, 0, 0.15)';
                        item.style.zIndex = '1';
                        item.style.opacity = '1';
                    } else {
                        // Hide non-matching items
                        item.style.display = 'none';
                    }
                }
            });
        });
    });
} 