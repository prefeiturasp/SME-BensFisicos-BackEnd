window.onload = function(){
    // esconde campo hora agendada e utiliza apenas para pegar valor atual na edição
    document.getElementsByClassName('field-hora_agendada')[0].style.display = "none";
    // esconde campo que define a url da api dinamicamente
    document.getElementsByClassName('field-url')[0].style.display = "none";

    // criação input select com label e opção padrão
    let divSelectHorarios = document.createElement('div');
    divSelectHorarios.className = 'form-row field-select_hora_agendada';
    
    let label = document.createElement('label')
    label.class = "required"
    label.for = "id_select_hora_agendada"
    label.innerHTML = "Horários disponíveis:"

    let select = document.createElement('select');
    select.name= "select_hora_agendada"
    select.id = id="id_select_hora_agendada"
    select.required = true
    select.onchange = onChangeSelect

    divSelectHorarios.appendChild(label);
    divSelectHorarios.appendChild(select);

    appendDefaultOption(select);
    
    // Adiciona campo select no formulário
    let fieldset = document.getElementsByTagName('fieldset')[0]
    let inputObs = document.getElementsByClassName('field-observacao')[0];
    fieldset.insertBefore(divSelectHorarios, inputObs);

    setupChangeForm();
};

// Sincroniza valor do input hora_agendada ao selecionar um horário.
function onChangeSelect(){
    let select = document.getElementById('id_select_hora_agendada');
    let inputHoraAgendada = document.getElementById('id_hora_agendada');
    inputHoraAgendada.value = select.value;
};

// Atualiza horários disponíveis, caso já tenha data preenchida.
// Adiciona valor atual do select.
function setupChangeForm(){
    let inputHoraAgendada = document.getElementById('id_hora_agendada');
    if (inputHoraAgendada.value){
        onChangeDate()
        appendOptionSelected(inputHoraAgendada.value)
    }
}

function appendOptionSelected(value) { 
    let select = document.getElementById('id_select_hora_agendada');
    let opt = document.createElement('option');
    opt.value = value
    opt.innerHTML = value
    opt.selected = true;
    select.appendChild(opt);    
}

function appendOptions(list) {
    let select = document.getElementById('id_select_hora_agendada');

    for(let i = 0; i < list.length; i++){
        let opt = document.createElement('option');
        opt.value = list[i]
        opt.innerHTML = list[i]
        select.appendChild(opt);
    }
    // Reset select caso não tenha nenhum horário disponível
    if(!list.length) {
        removeAllChildNodes(select);
        appendDefaultOption(select);
    }
};

function appendDefaultOption(select) {
    var default_option = document.createElement('option');
    default_option.value = ""
    default_option.selected
    default_option.innerHTML = "---------"
    select.appendChild(default_option)
};

function removeAllChildNodes(parent) {
    while (parent.firstChild) {
        parent.removeChild(parent.firstChild);
    }
}

function onChangeDate(){
    inputDate = document.getElementById("id_data_agendada");
    apiUrl = document.getElementById('id_url').value;

    fetch(`${apiUrl}/agenda/horarios_disponiveis/?data=${inputDate.value}`)
    .then(function(response) {
        return response.json();
    })
    .then(function(data) {
        appendOptions(data);
    })
    .catch()
};