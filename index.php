<!doctype html>
<html lang="en">
  <head>
    <!-- Required meta tags -->
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">

    <!-- Bootstrap CSS -->
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css" integrity="sha384-ggOyR0iXCbMQv3Xipma34MD+dH/1fQ784/j6cY/iJTQUOhcWr7x9JvoRxT2MZw1T" crossorigin="anonymous">

    <title>Spectrometer lock</title>
  </head>
  <body>
    <div class="container mt-5 shadow rounded p-4">
      <p id='status-text'>Spectrometer free</p>
      <p><button id="check-status-btn" class="btn btn-light">Check status</button></p>
      <p>
      <div class="form-group form-inline" id="unlocked">
        <div class="input-group">
          <label class="sr-only" for="name">Name:</label>
          <input type="text" class="form-control rounded mr-sm-4" id="name" placeholder="Your name">
          <button type="button" class="btn btn-success" id="lock-btn">Lock</button>
        </div>
      </div>
      <div class="form-group form-inline collapse", id="locked">
          <button type="button" class="btn btn-danger mb-2" id="unlock-btn">Unlock</button>
      </div>
      <div id="alert-div">
      </div>
    </div>
    </p>

    <!-- Optional JavaScript -->
    <!-- jQuery first, then Popper.js, then Bootstrap JS -->
    <script src="https://code.jquery.com/jquery-3.4.1.min.js"  integrity="sha256-CSXorXvZcTkaix6Yvo6HppcZGetbYMGWSFlBw8HfCJo="  crossorigin="anonymous"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.14.7/umd/popper.min.js" integrity="sha384-UO2eT0CpHqdSJQ6hJty5KVphtPhzWj9WO1clHTMGa3JDZwrnQq4sF86dIHNDz0W1" crossorigin="anonymous"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/js/bootstrap.min.js" integrity="sha384-JjSmVgyd0p3pXB1rRibZUAYoIIy6OrQ6VrjIEaFf/nJGzIxFDsf4x0xIM+B07jRM" crossorigin="anonymous"></script>
    <script>
    $(document).ready(function(){
      $("#lock-btn").click(function(){
        $.post("spectro_lock.php",
        {
          name:$("#name").val(),
          lock:' '
        },
        function(data, status){
          if (status == 'success') {
            data_array = data.split(',');
            if (data_array[0] == 'success-locked') {
              $("#locked").show();
              $("#unlocked").hide();
              $("#status-text").html("Spectrometer in use by " + data_array[1] + " since " + data_array[2]);
              $('#alert-div').html('')
              $('#check-status-btn').click();
            }
            else if (data_array[0] == 'err-already-locked') {
              $('#alert-div').html("<div class='alert alert-warning'>Couldn't lock: spectrometer already locked by someone else.</div>");
              $('#check-status-btn').click();
            }
          }
        });
      });

      $("#unlock-btn").click(function(){
        $.post("spectro_lock.php",
        {
          unlock:' '
        },
        function(data, status){
          if (status == 'success') {
            data_array = data.split(',');
            if (data_array[0] == 'success-unlocked') {
              $("#locked").hide();
              $("#unlocked").show();
              $("#status-text").html("Spectrometer free");
              $('#alert-div').html('')
            }
          }
        });
      });

      $("#check-status-btn").click(function(){
        $.post("spectro_lock.php",{},function(data,status) {
          if (status == 'success') {
            data_array = data.split(',');
            if (data_array[0] == 'unlocked') {
              $("#locked").hide();
              $("#unlocked").show();
              $("#status-text").html("Spectrometer free")
            }
            else if (data_array[0] == 'locked') {
              $("#locked").show();
              $("#unlocked").hide();
              $("#status-text").html("Spectrometer in use by " + data_array[1] + " since " + data_array[2]);
            }
          }
        });
      });

      $("#check-status-btn").click();
    });
  </script>
  </body>
</html>