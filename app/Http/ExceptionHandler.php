<?php

namespace App\Http;

use Exception;
use Laravel\Lumen\Exceptions\Handler;

class ExceptionHandler extends Handler
{
    protected $dontReport = [];

    public function report(Exception $e)
    {
        parent::report($e);
    }

    public function render($request, Exception $e)
    {
        return parent::render($request, $e);
    }
}