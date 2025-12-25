document.addEventListener('DOMContentLoaded', () => {
    // 1. 요소 가져오기
    const modal = document.getElementById('ai-modal');
    const aiBtn = document.getElementById('ai-btn'); // 상세페이지 버튼
    const aiBtnNav = document.getElementById('ai-btn-nav'); // 네비게이션 버튼
    const closeBtn = document.getElementsByClassName('close-btn')[0];
    const loading = document.getElementById('loading-spinner');
    const resultArea = document.getElementById('result-area');
    const progressBar = document.getElementById('ai-progress-bar');
    const progressText = document.getElementById('ai-progress-text');
    let progressTimer = null;
    const petSelectArea = document.getElementById('pet-select-area');
    const petSelectCards = document.querySelectorAll('.pet-select-card');
    const petSelectStartBtn = document.getElementById('pet-select-start');
    const petSelectWarning = document.getElementById('pet-select-warning');
    const productSizePicker = document.getElementById('product-size-picker');
    const productSizeDisplay = document.getElementById('product-size');
    const aiSizePicker = document.getElementById('ai-size-picker');
    const aiSizeDisplay = document.getElementById('ai-size');
    let selectedPetId = null;
    let selectedPetHasImage = false;
    
    // 모달 내부 요소
    const uploadPrompt = document.getElementById('upload-prompt');
    const modalSubmitBtn = document.getElementById('modal-submit-btn');
    const modalBreedInput = document.getElementById('modal-breed');
    const modalSizeInput = document.getElementById('modal-size'); 
    const modalFileInput = document.getElementById('modal-file');

    // 2. 모달 열기 함수
    function openModal() {
        modal.style.display = "block";
        resultArea.innerHTML = "";
        loading.style.display = "none";
        uploadPrompt.style.display = "none";

        if (petSelectArea && petSelectCards.length > 0) {
            petSelectArea.style.display = "block";
            if (!selectedPetId && petSelectCards[0]) {
                petSelectCards[0].click();
            }
        } else {
            uploadPrompt.style.display = 'block';
        }
    }

    if(aiBtn) aiBtn.onclick = openModal;
    if(aiBtnNav) aiBtnNav.onclick = (e) => { e.preventDefault(); openModal(); };

    // 3. 닫기 버튼
    if(closeBtn) {
        closeBtn.onclick = function() {
            closeModal();
        }
    }
    
    // 4. 모달 바깥 클릭
    window.onclick = function(event) {
        if (event.target == modal) {
            closeModal();
        }
    }

    function closeModal() {
        modal.style.display = "none";
        resultArea.innerHTML = ''; 
        uploadPrompt.style.display = "none"; 
        loading.style.display = "none";
        stopProgress();
        if (petSelectArea) {
            petSelectArea.style.display = "none";
        }
    }

    // 5. 'Start' 버튼 클릭 (정보 입력 후)
    if(modalSubmitBtn) {
        modalSubmitBtn.onclick = function() {
            const breed = modalBreedInput.value;
            const file = modalFileInput.files[0];
            const size = modalSizeInput ? modalSizeInput.value : null; 

            if(!breed) {
                alert("Please enter the dog breed!");
                return;
            }
            if(!file) {
                alert("Please select a photo!");
                return;
            }
            requestAIFitting(file, breed, size);
        }
    }

    if (petSelectCards.length > 0) {
        petSelectCards.forEach(card => {
            card.addEventListener('click', () => {
                petSelectCards.forEach(c => c.classList.remove('is-active'));
                card.classList.add('is-active');
                selectedPetId = card.dataset.petId;
                selectedPetHasImage = card.dataset.hasImage === "1";
                if (petSelectWarning) {
                    petSelectWarning.style.display = selectedPetHasImage ? "none" : "block";
                }
            });
        });
    }

    // AI 요청 함수
    function requestAIFitting(file = null, breed = null, size = null, petId = null) {
        loading.style.display = "block";
        startProgress();
        uploadPrompt.style.display = "none";
        if (petSelectArea) {
            petSelectArea.style.display = "none";
        }
        resultArea.innerHTML = "";

        const formData = new FormData();
        
        // 상세 페이지가 아닌 경우 예외처리 필요할 수 있음
        const productImgTag = document.getElementById('product-img');
        const productNameTag = document.getElementById('product-name');
        const productSizeTag = document.getElementById('product-size');
        const aiSizeTag = document.getElementById('ai-size');
        
        if(productImgTag) formData.append('product_image_url', productImgTag.src);
        if(productNameTag) formData.append('product_name', productNameTag.innerText);
        const fitSize = aiSizeTag && aiSizeTag.textContent ? aiSizeTag.textContent : (productSizeTag ? productSizeTag.innerText : null);
        if(fitSize) formData.append('product_size', fitSize);
        
        if (file) formData.append('user_image', file);
        if (breed) formData.append('pet_breed', breed);
        if (size) formData.append('pet_size', size);
        if (petId) formData.append('pet_id', petId);

        fetch('/api/fit_clothing', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            loading.style.display = "none";
            stopProgress();
            
            if (data.error === 'login_required') {
                alert('Login required!');
                window.location.href = '/login';
            } 
            else if (data.error === 'no_image') {
                uploadPrompt.style.display = "block";
            } 
            else if (data.success) {
                const img = document.createElement('img');
                img.src = data.result_image;
                img.style.maxWidth = "100%";
                img.style.borderRadius = "8px";
                img.style.boxShadow = "0 4px 12px rgba(0,0,0,0.1)";
                resultArea.appendChild(img);
                
                const msg = document.createElement('p');
                msg.textContent = data.message;
                msg.style.marginTop = "15px";
                msg.style.fontWeight = "bold";
                msg.style.color = "#7b2cbf";
                resultArea.appendChild(msg);
            } 
            else {
                if(data.result_image) {
                     const img = document.createElement('img');
                     img.src = data.result_image;
                     img.style.maxWidth = "100%";
                     resultArea.appendChild(img);
                }
                const msg = document.createElement('p');
                msg.textContent = data.message || 'Error occurred';
                msg.style.color = "red";
                resultArea.appendChild(msg);
            }
        })
        .catch(err => {
            console.error(err);
            loading.style.display = "none";
            stopProgress();
            alert('An error occurred during AI processing.');
        });
    }

    function startProgress() {
        if (!progressBar || !progressText) return;
        stopProgress();
        let value = 6;
        progressBar.style.width = value + "%";
        progressText.textContent = value + "%";
        progressTimer = setInterval(() => {
            value = Math.min(90, value + Math.floor(Math.random() * 6) + 2);
            progressBar.style.width = value + "%";
            progressText.textContent = value + "%";
        }, 450);
    }

    function stopProgress() {
        if (!progressBar || !progressText) return;
        if (progressTimer) {
            clearInterval(progressTimer);
            progressTimer = null;
        }
        progressBar.style.width = "100%";
        progressText.textContent = "100%";
    }

    function setupSizePicker(pickerEl, displayEl) {
        if (!pickerEl || !displayEl) return;
        const options = pickerEl.querySelectorAll('.size-option');
        const initialSize = displayEl.textContent.trim();
        if (initialSize) {
            options.forEach(option => {
                option.classList.toggle('is-active', option.dataset.size === initialSize);
            });
        }
        options.forEach(option => {
            option.addEventListener('click', () => {
                options.forEach(btn => btn.classList.remove('is-active'));
                option.classList.add('is-active');
                displayEl.textContent = option.dataset.size;
                const inputId = displayEl.dataset.inputId;
                if (inputId) {
                    const hiddenInput = document.getElementById(inputId);
                    if (hiddenInput) {
                        hiddenInput.value = option.dataset.size;
                    }
                }
            });
        });
    }

    setupSizePicker(productSizePicker, productSizeDisplay);
    setupSizePicker(aiSizePicker, aiSizeDisplay);

    if (petSelectStartBtn) {
        petSelectStartBtn.addEventListener('click', () => {
            if (!selectedPetId) {
                alert("Please select a pet profile.");
                return;
            }
            if (!selectedPetHasImage) {
                alert("Selected profile has no photo. Please update it in My Page.");
                return;
            }
            if (aiSizeDisplay) {
                aiSizeDisplay.textContent = aiSizeDisplay.textContent || "M";
            }
            requestAIFitting(null, null, null, selectedPetId);
        });
    }

    // ==========================================
    // [NEW] Currency Toggle Logic
    // ==========================================
    const currencyBtn = document.getElementById('currency-toggle');
    let isUSD = true; // Default

    if (currencyBtn) {
        currencyBtn.addEventListener('click', () => {
            isUSD = !isUSD;
            updateCurrency();
        });
        
        // Initialize currency on page load
        updateCurrency();
    }

    function updateCurrency() {
        const prices = document.querySelectorAll('.price-amount');
        const exchangeRate = 1300; // Example rate
        
        if (!currencyBtn) return;

        prices.forEach(priceEl => {
            const usdValue = parseFloat(priceEl.getAttribute('data-usd'));
            
            if (isUSD) {
                // Show USD
                currencyBtn.textContent = "$ USD";
                currencyBtn.classList.remove('active');
                priceEl.textContent = "$" + usdValue.toLocaleString();
            } else {
                // Show KRW
                const krwValue = Math.round(usdValue * exchangeRate);
                currencyBtn.textContent = "₩ KRW";
                currencyBtn.classList.add('active'); // Style change
                priceEl.textContent = "₩" + krwValue.toLocaleString();
            }
        });
    }

    // ==========================================
    // [NEW] Hero Carousel
    // ==========================================
    const carousel = document.querySelector('.hero-carousel');
    if (carousel) {
        const slides = carousel.querySelectorAll('.carousel-slide');
        const prevBtn = carousel.querySelector('.carousel-btn.prev');
        const nextBtn = carousel.querySelector('.carousel-btn.next');
        const intervalMs = parseInt(carousel.dataset.interval || '4000', 10);
        let current = 0;
        let timer = null;

        function showSlide(index) {
            if (slides.length === 0) return;
            current = (index + slides.length) % slides.length;
            slides.forEach((slide, i) => {
                slide.classList.toggle('is-active', i === current);
            });
        }

        function startAuto() {
            if (timer || slides.length < 2) return;
            timer = setInterval(() => {
                showSlide(current + 1);
            }, intervalMs);
        }

        function stopAuto() {
            if (timer) {
                clearInterval(timer);
                timer = null;
            }
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                stopAuto();
                showSlide(current - 1);
                startAuto();
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                stopAuto();
                showSlide(current + 1);
                startAuto();
            });
        }

        carousel.addEventListener('mouseenter', stopAuto);
        carousel.addEventListener('mouseleave', startAuto);

        showSlide(0);
        startAuto();
    }
});
