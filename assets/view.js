
CTFd._internal.challenge.data = undefined;

// TODO: Remove in CTFd v4.0
CTFd._internal.challenge.renderer = null;

CTFd._internal.challenge.preRender = function() {};

// TODO: Remove in CTFd v4.0
CTFd._internal.challenge.render = null;

CTFd._internal.challenge.postRender = function() {};

CTFd._internal.challenge.submit = function(preview) {
  var challenge_id = parseInt(CTFd.lib.$("#challenge-id").val());
  var submission = CTFd.lib.$("#challenge-input").val();

  var body = {
    challenge_id: challenge_id,
    submission: submission
  };
  var params = {};
  if (preview) {
    params["preview"] = true;
  }

  return CTFd.api.post_challenge_attempt(params, body).then(function(response) {
    if (response.status === 429) {
      // User was ratelimited but process response
      return response;
    }
    if (response.status === 403) {
      // User is not logged in or CTF is paused.
      return response;
    }
    return response;
  });
};


CTFd.plugin.run((_CTFd) => {
    const $ = _CTFd.lib.$
    const md = _CTFd.lib.markdown()
})

function setup_instance() {
  $.getJSON("/ctfdockerized/start/?challenge_info="+ challenge_id, function(result){        
    if (result["exists"] == true) {
      set_connexion_info(result["address"], result["port"], result["instance_id"]);
    }
  });
}


function start_instance() {
  $.getJSON("/ctfdockerized/start/?server=" + server_id + "&challenge="+ challenge_id, function(result){        
    if (result["success"] == false) {
      alert("An error occured, please contact the administrator.");
      return;
    }
    set_connexion_info(result["address"], result["port"], result["instance_id"]);
  });
}

function stop_instance() {
  instance_id = $('#instance-id')[0].attributes.value.value;
  $.getJSON("/ctfdockerized/stop/?instance_id=" + instance_id, function(result) {
    if (result["success"] == false) {
      alert("Can't stop the instance, please contact the administrator.");
      return;
    }
    reset_connexion_info();
  })
}

function reset_connexion_info() {
  $("#instance_data").html('<span><a onclick="start_instance(challenge_id, server_id);"'
          + 'class="btn btn-dark"> <small style="color:white;">'
          + '<i class="fas fa-play"></i> Start Instance</small>'
          + '</a></span>');
}

function set_connexion_info(addr, port, instance_id) {
  $("#instance_data").html('<div class="mt-2">Connexion info:<br /><b>'
          + addr + ":" + port + '</b></div><br />' + button
          + '<div id="instance-id" value=' + instance_id + '></div>');
}


let button = '<button type="button" onclick="stop_instance(challenge_id, server_id);" class="btn btn-outline-danger" data-toggle="tooltip" title="Stop Instance" id="instance-stop-button"><i class="btn-fa fas fa-stop"></i></button>'
