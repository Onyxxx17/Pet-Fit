document.addEventListener('DOMContentLoaded', () => {
    // 1. 요소 가져오기
    const modal = document.getElementById('ai-modal');
    const aiBtn = document.getElementById('ai-btn'); // 상세페이지 버튼
    const aiBtnNav = document.getElementById('ai-btn-nav'); // 네비게이션 버튼
    const closeBtn = document.getElementsByClassName('close-btn')[0];
    const loading = document.getElementById('loading-spinner');
    const resultArea = document.getElementById('result-area');
    
    // 모달 내부 요소
    const uploadPrompt = document.getElementById('upload-prompt');
    const modalSubmitBtn = document.getElementById('modal-submit-btn');
    const modalBreedInput = document.getElementById('modal-breed');
    const modalSizeInput = document.getElementById('modal-size'); 
    const modalFileInput = document.getElementById('modal-file');

    // 2. 모달 열기 함수
    function openModal() {
        modal.style.display = "block";
        // 상품 상세페이지가 아니면 기본 이미지나 안내를 보여줄 수도 있음
        // 여기서는 기존 로직대로 요청 시도 (로그인/프로필 체크를 위해)
        if(document.getElementById('product-img')) {
             requestAIFitting();
        } else {
            // 메인에서 눌렀을 때의 처리 (예: 임의의 상품이나 안내)
            // 현재는 간단히 프로필 체크만 수행하도록 함
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

    // AI 요청 함수
    function requestAIFitting(file = null, breed = null, size = null) {
        loading.style.display = "block";
        uploadPrompt.style.display = "none";
        resultArea.innerHTML = "";

        const formData = new FormData();
        
        // 상세 페이지가 아닌 경우 예외처리 필요할 수 있음
        const productImgTag = document.getElementById('product-img');
        const productNameTag = document.getElementById('product-name');
        
        if(productImgTag) formData.append('product_image_url', productImgTag.src);
        if(productNameTag) formData.append('product_name', productNameTag.innerText);
        
        if (file) formData.append('user_image', file);
        if (breed) formData.append('pet_breed', breed);
        if (size) formData.append('pet_size', size);

        fetch('/api/fit_clothing', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            loading.style.display = "none";
            
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
            alert('An error occurred during AI processing.');
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
    }

    function updateCurrency() {
        const prices = document.querySelectorAll('.price-amount');
        const exchangeRate = 1300; // Example rate

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
});