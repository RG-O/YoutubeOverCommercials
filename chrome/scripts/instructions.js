

const urlParameters = new URLSearchParams(window.location.search);
const oppositeMode = urlParameters.get('opposite_mode');

if (oppositeMode) {

    let regularModeElms = document.getElementById('regular-mode');
    regularModeElms.style.display = 'none';
    let oppositeModeElms = document.getElementById('opposite-mode');
    oppositeModeElms.style.display = 'block';

}